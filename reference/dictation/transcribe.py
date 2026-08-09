"""
transcribe.py — WAV to text, locally, via whisper.cpp.

Two passes, deliberately:

  1. `-dl`          detect the spoken language (cheap, and reliable even on
                    two-word clips: en p≈0.99, ar p≈0.95+).
  2. `-l <lang>`    transcribe with that language FORCED.

Pass 2 exists because Whisper is a multitask model trained on both *transcribe*
and *translate*. Left to choose, it picks the task by lottery on non-English
speech — the same Arabic phrase comes back as Arabic script, as an English
translation, or as a Latin transliteration, run to run. Detection is not the
unstable part; task selection is. Forcing the language removes the lottery.

See docs/01-pipeline.md for the flag-by-flag rationale.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import config
from .log import log

# whisper emits a placeholder for noise-only audio: "(silence)", "[BLANK_AUDIO]",
# a bare period, or nothing. All of these mean "no speech".
_EMPTY_RE = re.compile(r"[\[\(].*[\]\)]|\.|\s*")
_LANG_RE = re.compile(r"auto-detected language:\s*(\w+)\s*\(p\s*=\s*([0-9.]+)\)")


def clip_duration(wav: Path) -> float:
    """Seconds of audio, or 0.0 if unreadable."""
    res = subprocess.run(
        [config.FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(wav)],
        capture_output=True, text=True,
    )
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def detect_language(wav: Path) -> tuple[str, float]:
    """Language-detection-only pass. Returns (code, probability).

    Falls back to ('en', 0.0) if the line can't be parsed — a wrong guess of
    English is far less damaging than raising on an unexpected output format.
    """
    res = subprocess.run(
        [config.WHISPER_BIN, "-m", str(config.MODEL), "-dl", str(wav)],
        capture_output=True, text=True, timeout=120,
    )
    # Which stream this lands on varies by whisper.cpp version — search both.
    m = _LANG_RE.search(res.stderr + res.stdout)
    if m:
        return m.group(1), float(m.group(2))
    log(f"language detect parse failed; defaulting to en. stderr={res.stderr[:200]}")
    return "en", 0.0


def transcribe_forced(wav: Path, lang: str, vocab_prompt: str | None = None) -> str:
    """Transcribe with `lang` forced.

    The vocabulary bias prompt is applied for ENGLISH ONLY. An English prior on
    non-English audio pushes Whisper back toward translating — which is exactly
    the behaviour the forced language was added to prevent.
    """
    cmd = [
        config.WHISPER_BIN,
        "-m", str(config.MODEL),
        "--no-prints",   # stdout is the transcript and nothing else
        "-nt",           # no timestamps
        "-mc", "0",      # no cross-window text conditioning — see below
        "-l", lang,
    ]
    # -mc 0 is the repetition-loop guard. whisper.cpp normally conditions each
    # 30s decode window on previously-decoded text; a confidently-wrong token
    # then feeds itself forward and the decoder loops. Observed in production:
    # a six-word phrase emitted 56 times. This flag is separate from --prompt,
    # so vocabulary bias still applies.
    if lang == "en" and vocab_prompt:
        cmd += ["--prompt", vocab_prompt]
    cmd.append(str(wav))

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        log(f"transcribe[{lang}] FAILED rc={res.returncode}: {res.stderr[:300]}")
        return ""
    text = res.stdout.strip()
    if _EMPTY_RE.fullmatch(text):
        log(f"transcribe: empty/noise output: {text!r}")
        return ""
    return text


def load_vocab_prompt() -> str | None:
    """The whisper --prompt bias string, if one has been generated."""
    f = config.VOCAB_PROMPT_FILE
    if f.exists():
        s = f.read_text(encoding="utf-8").strip()
        return s or None
    return None


def transcribe(wav: Path) -> tuple[str, str]:
    """Full stage 1+2. Returns (text, language_code); text is '' on no speech."""
    if not wav.exists() or wav.stat().st_size == 0:
        log(f"missing or empty wav: {wav}")
        return "", "en"

    dur = clip_duration(wav)
    if dur < config.MIN_CLIP_SECONDS:
        # Whisper hallucinates a confident sentence out of 200ms of room tone.
        log(f"clip too short ({dur:.2f}s), discarding")
        return "", "en"

    lang, prob = detect_language(wav)
    log(f"detected language: {lang} (p={prob:.3f})")
    text = transcribe_forced(wav, lang, load_vocab_prompt())
    log(f"transcribed [{lang}] {len(text)} chars")
    return text, lang
