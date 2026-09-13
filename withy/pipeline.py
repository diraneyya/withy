"""
pipeline.py — the whole flow, in one place.

    WAV -> transcribe -> deterministic correction -> formatting -> history -> type

History is written BEFORE injection, always, so a dictation is recoverable even
when typing fails. Nothing in here raises: every stage degrades to the previous
stage's text, and the worst case is that the raw transcript gets typed.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import capture, config, correct, format as fmt, history, inject, speech, transcribe, vocab
from .log import log, set_state


def process(wav: Path, type_it: bool = True) -> dict:
    """Run a recorded take all the way to the screen. Returns the history record."""
    s = config.settings(reload=True)
    terms = vocab.load()

    # Cheap check before the expensive one: whisper invents a confident
    # sentence out of room tone, and typing "Thank you." when nothing was said
    # is worse than typing nothing.
    talking, spread = speech.has_speech(wav)
    if not talking:
        log(f"no speech detected (spread {spread:.1f} dB) — nothing typed")
        set_state("idle")
        return {}

    set_state("transcribing")
    t0 = time.time()
    raw, lang = transcribe.transcribe(wav, vocab.whisper_prompt(terms))
    transcribe_secs = time.time() - t0
    if not raw:
        log(f"no speech in {wav}")
        set_state("idle")
        return {}

    # With formatting enabled the model handles disfluency, which it does with
    # the context to tell a hedge from a noun. Doing it here first would only
    # risk damage the model cannot undo.
    post = bool(s["postprocess"])
    corrected, meta = correct.clean(raw, terms, disfluency=not post)

    format_secs = 0.0
    if post:
        set_state("formatting")
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
                 "words": len(raw.split())})
    rec = history.append(raw, corrected, final, meta, wav)
    log(f"[{lang}] {len(raw.split())}w raw -> {len(final.split())}w final "
        f"(transcribe {transcribe_secs:.1f}s, "
        f"{fmeta.get('backend')} polish {format_secs:.1f}s)")

    if type_it:
        # Clear the indicator BEFORE typing, so it can never sit over the field
        # being typed into.
        set_state("idle")
        if not inject.inject(final):
            log("typing failed — text is in history, recoverable from the menu")
    else:
        set_state("idle")
    return rec


def stop_and_process() -> dict:
    """What the hotkey calls on key-up."""
    wav = capture.stop()
    if wav is None:
        return {}
    try:
        return process(wav)
    except Exception as e:                                   # noqa: BLE001
        # Whatever broke, the audio is on disk and named in the log. Say so
        # loudly rather than dying silently with a stuck indicator.
        log(f"CRASHED: {type(e).__name__}: {e} — audio preserved at {wav}")
        set_state("idle")
        return {}
