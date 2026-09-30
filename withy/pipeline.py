"""
pipeline.py — the whole flow, in one place.

    WAV -> transcribe -> deterministic correction -> formatting -> history -> type

History is written BEFORE injection, always, so a dictation is recoverable even
when typing fails. Nothing in here raises: every stage degrades to the previous
stage's text, and the worst case is that the raw transcript gets typed.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from . import (capture, config, correct, format as fmt, history, inject,
               queue, screen, speech, transcribe, vocab)
from .log import log, set_state


def _phase(qid: str | None, phase: str) -> None:
    """Report progress against one queue row, or globally when unqueued."""
    if qid:
        queue.set_phase(qid, phase)
    else:
        set_state(phase)


# A recording at least this long that ends with nothing typed is announced and
# kept for `withy recover` — a lost dictation must be visible and one click
# from undoing, never only a line in the log.
RECOVER_MIN_SECONDS = 2.0


def _notify(title: str, text: str) -> None:
    from .inject import HS_BIN
    lua = (f"hs.notify.new({{title={json.dumps(title, ensure_ascii=False)}, "
           f"informativeText={json.dumps(text, ensure_ascii=False)}}}):send()")
    try:
        subprocess.run([HS_BIN or "hs", "-q", "-c", lua], capture_output=True,
                       timeout=4, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"notify failed: {e}")


def _nothing_typed(wav: Path, reason: str) -> dict:
    log(f"{reason} — nothing typed ({wav.name})")
    set_state("idle")
    secs = transcribe.clip_duration(wav)
    if secs >= RECOVER_MIN_SECONDS:
        try:
            config.DISCARDED_FILE.write_text(json.dumps(
                {"wav": str(wav), "reason": reason, "seconds": round(secs, 1),
                 "ts": time.strftime("%Y-%m-%d %H:%M:%S")}))
        except OSError as e:
            log(f"could not record discarded take: {e}")
        _notify("Withy: nothing typed",
                f"{secs:.0f} s recording, {reason}. Menu → Recover last recording.")
    return {}


def process(wav: Path, type_it: bool = True, qid: str | None = None,
            force: bool = False) -> dict:
    """Run a recorded take all the way to the screen.

    `qid` names this dictation's place in the queue, so its phase is
    reported against its own row rather than a single global state — which
    is what lets several be shown at once.
    """
    s = config.settings(reload=True)
    terms = vocab.load()

    # Whisper invents a confident "Thank you." out of room tone, so silence
    # must be caught before it. With the pause-detection model installed, that
    # model is the judge: on silence it hands whisper nothing and nothing comes
    # back. The loudness-spread check is only the fallback without the model —
    # it discarded real speech that scored 8-12 dB against a cut-off of 13.
    # `force` (recovery) skips every check.
    if force:
        log("recover: all speech checks skipped")
    elif config.VAD_MODEL.exists():
        spread = speech.modulation_spread(wav)
        log(f"speech: modulation spread {spread if spread is None else round(spread, 1)} dB "
            "(logged only; pause detection decides)")
    else:
        talking, spread = speech.has_speech(wav)
        if not talking:
            return _nothing_typed(wav, f"no speech detected (spread {spread:.1f} dB)")

    # Screen terms go to whisper ONLY — `terms` (which the polisher sees, and
    # which may be sent to a hosted backend) is deliberately left untouched.
    scr = screen.context() if s.get("screen_context") else None
    whisper_terms = list(terms) + (scr["terms"] if scr else [])
    wprompt = vocab.whisper_prompt(whisper_terms)
    if scr is not None:
        screen.write_report(scr, wprompt, "last dictation")
        scr = {k: v for k, v in scr.items() if k != "text"}
        log(f"screen: {scr['app']} ({scr['how']}, {scr['chars']} chars) -> "
            f"{len(scr['terms'])} terms: {', '.join(scr['terms'])}")
    log(f"whisper context: {wprompt}")

    _phase(qid, "transcribing")
    t0 = time.time()
    raw, lang = transcribe.transcribe(wav, wprompt, vad=not force)
    transcribe_secs = time.time() - t0
    if not raw:
        return _nothing_typed(wav, "no speech found by whisper")

    # With formatting enabled the model handles disfluency, and it handles the
    # vocabulary terms that NEED it — the ones whose garble is also ordinary
    # English. Doing those here first would risk damage the model cannot undo,
    # since a swap made here is invisible to it.
    #
    # Terms marked [deterministic] are the exception: their author has declared
    # that the words producing them could not be anything else, so exact
    # matching is safe and runs either way. They are corrected BEFORE the model
    # sees the text, which is also why they need no room in its term list.
    post = bool(s["postprocess"])
    det_terms, ctx_terms = vocab.split()
    corrected, meta = correct.clean(raw, det_terms if post else terms,
                                    disfluency=not post)

    format_secs = 0.0
    if post:
        _phase(qid, "formatting")
        t0 = time.time()
        final, fmeta = fmt.format_text(corrected, terms, lang)
        format_secs = time.time() - t0
    else:
        final, fmeta = corrected, {"applied": False, "reason": "disabled"}

    # Timings are recorded on every dictation, not just when something is being
    # debugged. They are what lets the app tell the user how long a backend
    # actually takes ON THEIR machine, instead of asking them to guess from a
    # table of somebody else's measurements.
    fmeta["seconds"] = round(format_secs, 2)
    fmeta["backend"] = str(s["polish_backend"]) if post else "off"
    meta.update({"lang": lang, "format": fmeta,
                 "transcribe_seconds": round(transcribe_secs, 2),
                 "words": len(raw.split()),
                 "whisper_prompt": wprompt})
    if scr is not None:
        meta["screen"] = scr
    rec = history.append(raw, corrected, final, meta, wav)
    log(f"[{lang}] {len(raw.split())}w raw -> {len(final.split())}w final "
        f"(transcribe {transcribe_secs:.1f}s, "
        f"{fmeta.get('backend')} polish {format_secs:.1f}s)")

    if type_it:
        # Clear the indicator BEFORE typing, so it can never sit over the field
        # being typed into.
        if qid:
            queue.finish(qid, drop_audio=False)
        set_state("idle")
        if not inject.inject(final):
            log("typing failed — text is in history, recoverable from the menu")
    else:
        if qid:
            queue.finish(qid, drop_audio=False)
        set_state("idle")
    return rec


def stop_and_process() -> dict:
    """What the hotkey calls on key-up.

    The recording joins the queue FIRST and is processed second, and those are
    deliberately separate steps. Queueing is instant, so the key is free again
    immediately — you can start speaking the next thing while this one is still
    being transcribed. Draining then happens under a lock that guarantees the
    results are typed in the order they were spoken, whichever process wins it.
    """
    qid = queue.oldest_recording()
    if qid is None:
        log("stop: nothing recording")
        return {}
    wav = capture.stop(qid)
    if wav is None:
        queue.cancel_recording(qid)
        return {}
    queue.enqueue(wav, qid)
    last: dict = {}

    def handle(path: Path, item_id: str) -> None:
        nonlocal last
        # Move the recording to its permanent home BEFORE processing, so the
        # path history records is the path that will still be there afterwards.
        kept = config.AUDIO_DIR / f"take-{item_id}.wav"
        try:
            config.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            path.replace(kept)
        except OSError:
            kept = path
        try:
            last = process(kept, qid=item_id) or last
        except Exception as e:                               # noqa: BLE001
            # Whatever broke, the audio is on disk and named in the log. Say so
            # loudly rather than dying silently with a stuck indicator.
            log(f"CRASHED: {type(e).__name__}: {e} — audio preserved at {kept}")
            set_state("idle")

    # Zero means another process already holds the lock and will take our file
    # with it. That is the normal fast-typing case, not a failure.
    queue.drain(handle)
    return last
