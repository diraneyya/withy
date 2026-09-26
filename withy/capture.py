"""
capture.py — microphone to a Whisper-ready WAV.

16 kHz mono is Whisper's native input. Resample at capture, not later.

THE DEVICE-SELECTION TRAP, which costs everyone a day: `-i ":0"` looks correct
and is wrong. Index 0 is the first ENUMERATED device, not the system default.
On any machine with BlackHole, Loopback, Krisp or an aggregate device installed
— most developer laptops — index 0 is often a multi-channel aggregate. ffmpeg
refuses to auto-downmix an unknown high-channel layout and writes a ZERO-BYTE
WAV with exit code 0. The symptom is "dictation does nothing", with no error
anywhere. So devices are always resolved by name, and the result is verified.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from . import config
from .log import log, set_state

_DEV_RE = re.compile(r"^\[AVFoundation.*?\]\s*\[(\d+)\]\s*(.+)$")
# Ordered preference when picking a microphone automatically. Built-in hardware
# first; virtual/aggregate devices are what the zero-byte trap is made of.
_PREFERRED = ("macbook", "built-in", "internal", "imac", "studio display")

# THE CHIRP MUST NOT LIE. Opening an audio device on macOS costs ~310 ms, and
# occasionally over a second — measured 2026-09-26: ffmpeg's own startup is
# ~30 ms of that and Withy's bookkeeping 19 ms; the rest is CoreAudio, and a
# hand-written AVAudioEngine recorder was no faster, so this is simply the
# price. Everything said before the first sample is absent from the WAV, and
# the "don't" at the front of a dictation is exactly the word that must not
# vanish. So start() does not return until there is encoded audio, and the
# chirp that invites you to speak hangs off that return.
#
# The liveness signal is ffmpeg's -progress report, NOT the WAV's size: the
# muxer buffers 32 KB before it touches the disk, so the file sits at its
# 44-byte header for over four seconds while audio is being captured fine.
FIRST_SAMPLE_TIMEOUT = 5.0


def list_mics() -> list[str]:
    """Audio input device names, in enumeration order."""
    res = subprocess.run(
        [config.FFMPEG_BIN, "-hide_banner", "-f", "avfoundation",
         "-list_devices", "true", "-i", ""],
        capture_output=True, text=True,
    )
    names, in_audio = [], False
    for line in res.stderr.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if "AVFoundation video devices" in line:
            in_audio = False
            continue
        m = _DEV_RE.match(line.strip())
        if in_audio and m:
            names.append(m.group(2).strip())
    return names


def _pick_mic() -> str:
    """Enumerate devices and choose one. SLOW — 0.15-1.0s, because it spins up
    the whole AVFoundation stack. Never call this on the recording path."""
    mics = list_mics()
    want = str(config.settings()["mic"])
    if want and want != "default":
        for n in mics:
            if want.lower() in n.lower():
                return n
        log(f"configured mic {want!r} not found; falling back")
    for pref in _PREFERRED:
        for n in mics:
            if pref in n.lower():
                return n
    return mics[0] if mics else "default"


def resolve_mic(refresh: bool = False) -> str:
    """The device name to record from — cached, because enumerating costs up to
    a second and that second is speech the user has already started saying.

    This was measured: device enumeration on every key-press was the dominant
    part of the gap between pressing the key and audio actually being captured,
    and it is what made the first few words of a dictation disappear.
    """
    s = config.settings()
    want = str(s["mic"])
    if not refresh:
        if want and want != "default":
            return want          # ffmpeg matches the name as a substring
        cached = str(s.get("resolved_mic") or "")
        if cached:
            return cached
    name = _pick_mic()
    config.save_settings({"resolved_mic": name})
    return name


def is_recording() -> bool:
    if not config.PID_FILE.exists():
        return False
    try:
        os.kill(int(config.PID_FILE.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def part_path(qid: str) -> Path:
    """Where this take is being written while the microphone is open."""
    return config.QUEUE_DIR / f"{qid}.part.wav"


def pid_path(qid: str) -> Path:
    return config.QUEUE_DIR / f"{qid}.pid"


def progress_path(qid: str) -> Path:
    """Where ffmpeg reports what it has actually encoded."""
    return config.QUEUE_DIR / f"{qid}.progress"


def _is_live(qid: str) -> bool:
    """True once ffmpeg says it has encoded a non-zero amount of audio."""
    try:
        for line in progress_path(qid).read_text(encoding="utf-8").splitlines():
            if line.startswith("out_time_us="):
                value = line.split("=", 1)[1].strip()
                if value.isdigit() and int(value) > 0:
                    return True
    except OSError:
        pass
    return False


def _wait_until_live(qid: str, proc: subprocess.Popen) -> bool:
    """Block until the microphone is really delivering, or give up saying so."""
    deadline = time.monotonic() + FIRST_SAMPLE_TIMEOUT
    while time.monotonic() < deadline:
        if _is_live(qid):
            return True
        if proc.poll() is not None:
            # The recorder is gone before it produced anything. If its pid file
            # went with it, a `stop` owned this take and ended it deliberately —
            # a press too short to reach the first sample, not a failure.
            if not pid_path(qid).exists():
                return True
            log(f"record failed: recorder exited rc={proc.returncode} with no audio")
            return False
        time.sleep(0.005)
    log(f"record failed: no audio within {FIRST_SAMPLE_TIMEOUT:.0f}s — wedged input device?")
    return False


def start(qid: str) -> bool:
    """Begin recording take `qid`, returning only once audio is really flowing.

    EVERY TAKE GETS ITS OWN FILES. There used to be one shared WAV and one
    shared pid file, and `start()` began by cancelling whatever was running —
    which was correct for one-at-a-time dictation and catastrophic once a second
    press could arrive while the first take was still being closed. `stop()`
    ends ffmpeg with SIGINT so it can flush the WAV header; the new `start()`
    arriving a moment later SIGKILLed that same process, leaving a header-less
    file whisper cannot read. The symptom was an empty take and a queue card
    that appeared and vanished.

    So: no cancel, no shared paths. A recorder is only ever stopped by the stop
    that owns it, or reaped long afterwards if its key-up was lost.
    """
    config.ensure_dirs()
    config.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    wav = part_path(qid)
    wav.unlink(missing_ok=True)
    progress_path(qid).unlink(missing_ok=True)
    mic = resolve_mic()
    log(f"record start {qid} mic={mic!r}")
    proc = subprocess.Popen(
        [config.FFMPEG_BIN, "-hide_banner", "-loglevel", "error", "-nostdin",
         "-progress", str(progress_path(qid)), "-stats_period", "0.05",
         "-f", "avfoundation", "-i", f":{mic}",
         "-ar", "16000", "-ac", "1", "-y", str(wav)],
        stdout=subprocess.DEVNULL,
        stderr=config.LOG_FILE.open("a"),
        start_new_session=True,
    )
    pid_path(qid).write_text(str(proc.pid))
    return _wait_until_live(qid, proc)


def stop(qid: str) -> Path | None:
    """End take `qid` and return its WAV, or None if there is nothing usable.

    The returned path IS the queue entry — the recording is written straight
    into the queue directory, so there is no later move that a racing recorder
    could collide with.
    """
    pf = pid_path(qid)
    if not pf.exists():
        log(f"stop: {qid} has no recorder")
        progress_path(qid).unlink(missing_ok=True)
        return None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        pid = 0
    pf.unlink(missing_ok=True)

    if pid:
        try:
            # SIGINT, not SIGKILL: ffmpeg must flush the WAV header. A killed
            # recorder leaves a header-less file whisper cannot read at all.
            os.kill(pid, signal.SIGINT)
            for _ in range(30):
                time.sleep(0.1)
                os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    progress_path(qid).unlink(missing_ok=True)
    wav = part_path(qid)
    if not wav.exists() or wav.stat().st_size == 0:
        log("stop: WAV empty — stale input device? clearing the cached mic")
        config.save_settings({"resolved_mic": ""})
        wav.unlink(missing_ok=True)
        return None

    # Renamed within the same directory, so it becomes a queue entry atomically.
    kept = config.QUEUE_DIR / f"{qid}.wav"
    try:
        wav.replace(kept)
    except OSError:
        kept = wav
    return kept


def cancel(qid: str | None = None) -> None:
    """Discard a take. With no id, discards every recorder that is running."""
    ids = [qid] if qid else [f.stem for f in config.QUEUE_DIR.glob("*.pid")] \
        if config.QUEUE_DIR.exists() else []
    for i in ids:
        pf = pid_path(i)
        try:
            os.kill(int(pf.read_text().strip()), signal.SIGKILL)
        except (OSError, ValueError):
            pass
        pf.unlink(missing_ok=True)
        part_path(i).unlink(missing_ok=True)
        progress_path(i).unlink(missing_ok=True)
    set_state("idle")


def purge_audio(keep_days: int) -> int:
    """Delete kept takes older than `keep_days`. Returns the count removed."""
    if keep_days <= 0:
        return 0
    cutoff = time.time() - keep_days * 86400
    n = 0
    for f in config.AUDIO_DIR.glob("take-*.wav"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            pass
    return n
