"""
queue.py — more than one dictation in flight at a time.

THE POINT. Speaking is fast and transcribing is not. Without a queue, the
seconds after you let go are dead: press again and you either lose the press or
corrupt the take that is still being processed. With one, you keep talking and
the machine catches up behind you. The wait stops being a wall and becomes a
backlog you can see.

THE SHAPE. There is no daemon and no server. A directory IS the queue, and each
file's name says what stage its dictation has reached:

    <id>.recording     the microphone is open, right now
    <id>.wav           spoken, waiting its turn
    <id>.phase         being worked on; the file says transcribing/formatting/typing

`<id>` is a sortable timestamp, so "oldest first" is a directory listing and
FIFO needs no bookkeeping. Anything that wants to know what is happening —
the menubar, the banner, a person with `ls` — reads the directory.

ORDER IS THE WHOLE GUARANTEE. Each `withy stop` is its own process, so two of
them racing would type their results in whatever order they finished, and a
short dictation would overtake a long one. Text arriving in a different order
from the words you said is worse than waiting. So a process that has queued its
recording takes an exclusive lock and then drains EVERYTHING pending in id
order, not just its own. Whichever process wins the lock, the output order is
the order you spoke — and a process that loses the lock simply exits, because
the winner will pick up its file.

flock is released by the kernel when the holder dies, so a crash costs the
queue nothing: the next dictation acquires the lock and drains what was left.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path

from . import config
from .log import log

PHASES = ("recording", "queued", "transcribing", "formatting", "typing")

# Read by the Spoon to draw the banner stack. In /tmp because it is worthless
# across a reboot and must never be mistaken for data.
STATE_FILE = Path("/tmp/withy-queue.json")


def _dir() -> Path:
    config.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    return config.QUEUE_DIR


def new_id() -> str:
    """Sortable, unique, and readable in a directory listing."""
    return time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1e6) % 1000000:06d}"


def entries() -> list[dict]:
    """Everything in flight, oldest first."""
    d = _dir()
    items: dict[str, str] = {}
    for f in d.iterdir():
        if f.suffix == ".recording":
            items[f.stem] = "recording"
        elif f.suffix == ".wav" and not f.name.endswith(".part.wav"):
            items.setdefault(f.stem, "queued")
        elif f.suffix == ".phase":
            try:
                phase = f.read_text(encoding="utf-8").strip()
            except OSError:
                phase = "transcribing"
            items[f.stem] = phase if phase in PHASES else "transcribing"
    return [{"id": k, "phase": items[k]} for k in sorted(items)]


def publish() -> None:
    """Rewrite the state file from the directory.

    Every writer recomputes the WHOLE state from the filesystem rather than
    editing a shared structure, so concurrent writers cannot disagree: they are
    all reading the same source of truth, and the last one to land is right.
    Written to a temp file and renamed, so a reader never sees half of it.
    """
    try:
        items = entries()
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": items}), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
        # The single-phase file predates the queue and other things still read
        # it; keep it pointing at whatever is actually being worked on.
        working = next((i for i in items if i["phase"] not in ("queued",)), None)
        config.STATE_FILE.write_text(working["phase"] if working else "idle",
                                     encoding="utf-8")
    except OSError as e:
        log(f"queue: could not publish state ({e})")


def start_recording() -> str:
    """Claim an id and show it as recording. Called when the key goes down."""
    qid = new_id()
    (_dir() / f"{qid}.recording").write_text("", encoding="utf-8")
    publish()
    return qid


def oldest_recording() -> str | None:
    """The take a stop should close.

    OLDEST, not newest. Key-up and the next key-down are separate processes and
    can land in either order, so for a moment two `.recording` markers can
    exist. The one being released is always the one that started first; taking
    the newest would close the take the user has only just begun speaking.
    """
    rec = sorted(_dir().glob("*.recording"))
    return rec[0].stem if rec else None


def cancel_recording(qid: str | None = None) -> None:
    qid = qid or oldest_recording()
    if qid:
        (_dir() / f"{qid}.recording").unlink(missing_ok=True)
    publish()


def enqueue(wav: Path, qid: str) -> str:
    """Mark a finished recording as ready.

    The recorder already wrote it into the queue directory under this id, so
    there is nothing to move — only the `.recording` marker to drop, which is
    what turns the row from "Recording" into "Queued".
    """
    if wav.parent != _dir():
        try:
            wav.replace(_dir() / f"{qid}.wav")
        except OSError:
            pass
    (_dir() / f"{qid}.recording").unlink(missing_ok=True)
    publish()
    return qid


def set_phase(qid: str, phase: str) -> None:
    (_dir() / f"{qid}.phase").write_text(phase, encoding="utf-8")
    publish()


def finish(qid: str, drop_audio: bool = True) -> None:
    """Remove a row. `drop_audio=False` clears the indicator but keeps the WAV.

    The recording is the only copy of what was said and history points at it, so
    whoever is processing the take owns moving it somewhere permanent. Deleting
    it here as part of clearing the banner is how history ended up referencing a
    file that no longer existed — which silently broke Retry.
    """
    suffixes = (".phase", ".recording", ".wav") if drop_audio else (".phase", ".recording")
    for suffix in suffixes:
        (_dir() / f"{qid}{suffix}").unlink(missing_ok=True)
    publish()


def _clear_stale_phases() -> None:
    """Drop phase markers nobody is working on.

    ONLY SAFE WHILE HOLDING THE DRAIN LOCK. A phase file with no recording
    beside it is the normal state of the take being processed right now — the
    handler moves the WAV to its permanent home before starting — so the two
    cases are indistinguishable from the filesystem alone. The lock is what
    separates them: if we hold it, nobody is working, so anything left is a
    marker whose process died, and it would otherwise sit in the banner stack
    saying "Transcribing" forever.
    """
    for f in _dir().glob("*.phase"):
        if not (_dir() / f"{f.stem}.wav").exists():
            f.unlink(missing_ok=True)


def pending() -> list[tuple[str, Path]]:
    """Finished recordings awaiting work, oldest first.

    `.part.wav` is a microphone that is still open. Draining one would transcribe
    a sentence the user is halfway through saying.
    """
    d = _dir()
    return [(f.stem, f) for f in sorted(d.glob("*.wav"))
            if not f.name.endswith(".part.wav")]


def drain(handle) -> int:
    """Process everything pending, oldest first, under an exclusive lock.

    `handle(wav, qid)` does the real work. Returns how many were processed —
    zero means another process holds the lock and is handling them, which is
    not an error and not something to retry.
    """
    lock_path = _dir() / ".lock"
    lock = open(lock_path, "w")                                # noqa: SIM115
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Someone else is draining. They will find our file, because it was
        # written to the queue BEFORE we tried for the lock.
        lock.close()
        return 0
    done = 0
    try:
        _clear_stale_phases()
        publish()
        while True:
            items = pending()
            if not items:
                break
            qid, wav = items[0]
            # Anchor the row on its phase file before the handler moves the
            # recording out of the queue, or the row would blink out of the
            # banner stack for as long as the move takes.
            set_phase(qid, "transcribing")
            try:
                handle(wav, qid)
            except Exception as e:                             # noqa: BLE001
                log(f"queue: {qid} failed: {type(e).__name__}: {e}")
            finally:
                finish(qid)
            done += 1
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    return done


def reap(max_age_hours: float = 6.0) -> None:
    """Clear anything a killed process left behind.

    A `.recording` marker outlives a crashed recorder, and a stale one would
    show a banner for a microphone that is not open.
    """
    # A recorder whose key-up was lost keeps ffmpeg running and its marker
    # showing "Recording" forever. Kill any whose process is already gone, and
    # any that has been open implausibly long.
    import os as _os
    try:
        for pf in list(_dir().glob("*.pid")):
            try:
                pid = int(pf.read_text().strip())
                _os.kill(pid, 0)
                alive = True
            except (OSError, ValueError):
                alive = False
            if not alive:
                qid = pf.stem
                pf.unlink(missing_ok=True)
                (_dir() / f"{qid}.recording").unlink(missing_ok=True)
                (_dir() / f"{qid}.part.wav").unlink(missing_ok=True)
    except OSError:
        pass

    # Only meaningful when nothing is draining; if the lock is taken, every
    # phase marker belongs to a take being worked on this instant.
    try:
        lock = open(_dir() / ".lock", "w")                      # noqa: SIM115
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _clear_stale_phases()
            fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            lock.close()
    except OSError:
        pass

    cutoff = time.time() - max_age_hours * 3600
    try:
        for f in _dir().iterdir():
            if f.name == ".lock":
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
            except OSError:
                continue
    except OSError:
        return
    publish()
