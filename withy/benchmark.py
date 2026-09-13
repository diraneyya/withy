"""
benchmark.py — comparable timings, from fixed input.

The per-dictation timings elsewhere answer "how long did that take". They cannot
answer "which of these is faster", because every dictation is a different length
of different speech. Printing a median from them next to a model name reads as a
benchmark and is not one.

This is the honest version: every model gets the SAME input, so the numbers can
be compared and quoted.

Two reference inputs:

  speech   one of the user's own recordings, kept aside the first time a
           benchmark runs. Their voice, their microphone, their room — a stock
           sample would measure how well a model handles someone else.
  polish   a fixed transcript, built in, deliberately containing the things
           polishing is for: filler, a stutter, a spoken retraction, reported
           speech and a spoken enumeration. Being identical everywhere also
           makes results comparable between machines.

What it does NOT measure: quality. It reports each transcript and each polished
result in full so a person can judge that themselves, because nothing here can.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import config, format as fmt, transcribe, vocab
from .log import log

REFERENCE_WAV = config.DATA_DIR / "benchmark" / "reference.wav"
RESULTS = config.DATA_DIR / "benchmark" / "results.json"

# Deliberately messy: filler, a stutter, a retraction, reported speech, and an
# enumeration — one of each thing polishing exists to handle.
POLISH_REFERENCE = (
    "um so the the thing i wanted to say is that we should meet on monday "
    "no scratch that lets meet on tuesday at three and then she said well "
    "that depends on the weather which i thought was fair enough what i need "
    "from this is three things it has to be quick it has to be private and it "
    "has to work when the wifi is down you know what i mean"
)


def _pick_reference(min_seconds: float = 4.0) -> Path | None:
    """Keep one real recording aside as the fixed input, once.

    Chosen from the user's own takes rather than shipped with the tool: a
    benchmark on somebody else's voice measures the wrong thing.
    """
    if REFERENCE_WAV.exists():
        return REFERENCE_WAV
    takes = sorted(config.AUDIO_DIR.glob("take-*.wav"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    for t in takes:
        if transcribe.clip_duration(t) >= min_seconds:
            REFERENCE_WAV.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(t, REFERENCE_WAV)
            log(f"benchmark: reference audio taken from {t.name}")
            return REFERENCE_WAV
    return None


def speech(models: list[dict] | None = None) -> list[dict]:
    """Time every installed speech model on the same recording."""
    wav = _pick_reference()
    if wav is None:
        return []
    models = models if models is not None else transcribe.speech_models()
    prompt = vocab.whisper_prompt(vocab.load())
    original = config.settings()["whisper_model"]
    out = []
    try:
        for m in models:
            config.save_settings({"whisper_model": m["path"]})
            config.settings(reload=True)
            t0 = time.time()
            text, _lang = transcribe.transcribe(wav, prompt)
            out.append({"model": m["name"], "size_mb": m["size_mb"],
                        "seconds": round(time.time() - t0, 2),
                        "words": len(text.split()), "text": text})
    finally:
        # Always put the user's choice back, including on Ctrl-C.
        config.save_settings({"whisper_model": original})
        config.settings(reload=True)
    return out


def _polish_candidates() -> list[tuple[str, str]]:
    """(backend, label) for every option that could actually run right now."""
    out = []
    for m in (fmt.ollama_models() or []):
        out.append(("local:" + m, f"local model {m}"))
    argv = fmt.detect_cli()
    if argv:
        # argv[0] is the resolved absolute path; show the name a person typed.
        pretty = " ".join([Path(argv[0]).name] + argv[1:])
        out.append(("command", "local CLI: " + pretty))
    for provider in ("openai", "anthropic"):
        if fmt.has_key(provider):
            model = config.settings().get(
                fmt.PROVIDERS[provider]["model_setting"], "")
            out.append((provider, f"{fmt.PROVIDERS[provider]['label']} API {model}"))
    return out


def polish() -> list[dict]:
    """Run the same transcript through every polishing option available."""
    before = {k: config.settings()[k] for k in ("polish_backend", "llm_model",
                                                "postprocess")}
    terms = vocab.load()
    out = []
    try:
        for backend, label in _polish_candidates():
            settings = {"postprocess": True}
            if backend.startswith("local:"):
                settings["polish_backend"] = "local"
                settings["llm_model"] = backend.split(":", 1)[1]
            else:
                settings["polish_backend"] = backend
            config.save_settings(settings)
            config.settings(reload=True)
            t0 = time.time()
            text, meta = fmt.format_text(POLISH_REFERENCE, terms)
            out.append({"backend": label, "seconds": round(time.time() - t0, 2),
                        "applied": bool(meta.get("applied")),
                        "text": text})
    finally:
        config.save_settings(before)
        config.settings(reload=True)
    return out


def save(results: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                       encoding="utf-8")


def load() -> dict:
    try:
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
