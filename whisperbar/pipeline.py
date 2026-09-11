"""
pipeline.py — the whole flow, in one place.

    WAV -> transcribe -> deterministic correction -> formatting -> history -> type

History is written BEFORE injection, always, so a dictation is recoverable even
when typing fails. Nothing in here raises: every stage degrades to the previous
stage's text, and the worst case is that the raw transcript gets typed.
"""

from __future__ import annotations

from pathlib import Path

from . import capture, config, correct, format as fmt, history, inject, transcribe, vocab
from .log import log, set_state


def process(wav: Path, type_it: bool = True) -> dict:
    """Run a recorded take all the way to the screen. Returns the history record."""
    s = config.settings(reload=True)
    terms = vocab.load()

    set_state("transcribing")
    raw, lang = transcribe.transcribe(wav, vocab.whisper_prompt(terms))
    if not raw:
        log(f"no speech in {wav}")
        set_state("idle")
        return {}

    # With formatting enabled the model handles disfluency, which it does with
    # the context to tell a hedge from a noun. Doing it here first would only
    # risk damage the model cannot undo.
    post = bool(s["postprocess"])
    corrected, meta = correct.clean(raw, terms, disfluency=not post)

    if post:
        set_state("formatting")
        final, fmeta = fmt.format_text(corrected, terms, lang)
    else:
        final, fmeta = corrected, {"applied": False, "reason": "disabled"}

    meta.update({"lang": lang, "format": fmeta})
    rec = history.append(raw, corrected, final, meta, wav)
    log(f"[{lang}] {len(raw.split())}w raw -> {len(final.split())}w final "
        f"(format={fmeta.get('applied')})")

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
