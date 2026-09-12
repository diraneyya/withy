"""
transcribe.py — WAV to text, locally, via whisper.cpp.

Two passes, deliberately:

  1. `-dl`         detect the spoken language. Cheap and reliable even on very
                   short clips (en p~0.99, ar p~0.95).
  2. `-l <lang>`   transcribe with that language FORCED.

Pass 2 exists because Whisper is a multitask model trained on transcribe AND
translate. Left to choose, it picks by lottery on non-English speech: the same
Arabic sentence returns as Arabic script, as an English translation, or as a
Latin transliteration, run to run. Detection is not the unstable part; task
selection is. Forcing the language removes the lottery.

When the user has pinned a language in settings, pass 1 is skipped entirely —
that halves the work, because most of the wall-clock here is loading the model.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import config
from .log import log

# Whisper emits a placeholder for noise-only audio: "(silence)", "[BLANK_AUDIO]",
# a bare period, or nothing at all. All mean "no speech".
_EMPTY_RE = re.compile(r"[\[\(].*[\]\)]|\.|\s*")
_LANG_RE = re.compile(r"auto-detected language:\s*(\w+)\s*\(p\s*=\s*([0-9.]+)\)")


def clip_duration(wav: Path) -> float:
    res = subprocess.run(
        [config.FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(wav)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def detect_language(wav: Path, model: str) -> tuple[str, float]:
    res = subprocess.run([config.WHISPER_BIN, "-m", model, "-dl", str(wav)],
                         capture_output=True, text=True, timeout=120)
    # Which stream this lands on varies by whisper.cpp build — search both.
    m = _LANG_RE.search(res.stderr + res.stdout)
    if m:
        return m.group(1), float(m.group(2))
    log(f"language detect unparsed; defaulting to en. stderr={res.stderr[:200]}")
    return "en", 0.0


def transcribe_forced(wav: Path, lang: str, model: str, prompt: str | None) -> str:
    cmd = [config.WHISPER_BIN, "-m", model,
           "--no-prints",   # stdout is the transcript and nothing else
           "-nt",           # no timestamps
           "-mc", "0",      # no cross-window conditioning — the loop guard
           "-l", lang]
    # -mc 0: whisper.cpp normally conditions each 30s window on previously
    # decoded text, so a confidently-wrong token feeds itself forward and the
    # decoder loops (recorded worst case: a six-word phrase 56 times).
    #
    # The vocabulary prompt is applied for ENGLISH ONLY. An English prior on
    # non-English audio pushes the model back toward translating, which is
    # exactly what forcing the language was added to prevent.
    if lang == "en" and prompt:
        cmd += ["--prompt", prompt]
    cmd.append(str(wav))

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        log(f"transcribe[{lang}] FAILED rc={res.returncode}: {res.stderr[:300]}")
        return ""
    text = res.stdout.strip()
    if _EMPTY_RE.fullmatch(text):
        log(f"transcribe: empty/noise output {text!r}")
        return ""
    return text


def transcribe(wav: Path, prompt: str | None = None) -> tuple[str, str]:
    """Returns (text, language). text is '' when there is no speech."""
    s = config.settings()
    model = str(s["whisper_model"])
    if not Path(model).exists():
        log(f"whisper model missing: {model}")
        return "", "en"
    if not wav.exists() or wav.stat().st_size == 0:
        log(f"missing or empty wav: {wav}")
        return "", "en"

    dur = clip_duration(wav)
    if dur < float(s["min_clip_seconds"]):
        # Whisper will hallucinate a confident sentence out of 200ms of room tone.
        log(f"clip too short ({dur:.2f}s) — discarding")
        return "", "en"

    pinned = str(s["language"])
    if pinned and pinned != "auto":
        lang = pinned
    else:
        lang, prob = detect_language(wav, model)
        log(f"language {lang} (p={prob:.3f})")
    return transcribe_forced(wav, lang, model, prompt), lang
