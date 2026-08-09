"""
config.py — every path and knob in one place, all overridable by environment.

The original system had absolute paths baked into five different files, which is
why it worked on exactly one machine. Everything resolves here instead.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _env_path(name: str, default: str | None) -> Path | None:
    v = os.environ.get(name)
    if v:
        return Path(v).expanduser()
    return Path(default).expanduser() if default else None


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


# ── binaries ────────────────────────────────────────────────────────────────
# whisper.cpp's CLI. Homebrew installs it as `whisper-cli`; older builds and
# some source builds call it `main`.
WHISPER_BIN = os.environ.get("DICTATION_WHISPER_BIN") or _which("whisper-cli", "whisper-cpp") or "whisper-cli"
FFMPEG_BIN = os.environ.get("DICTATION_FFMPEG_BIN") or _which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = os.environ.get("DICTATION_FFPROBE_BIN") or _which("ffprobe") or "ffprobe"

# ── model ───────────────────────────────────────────────────────────────────
# ggml-format Whisper weights. large-v3-turbo (1.6 GB) is the accuracy/speed
# sweet spot on Apple Silicon; base.en (148 MB) is the low-resource option.
MODEL = _env_path(
    "DICTATION_MODEL",
    "/opt/homebrew/share/whisper-cpp/ggml-large-v3-turbo.bin",
)

# ── application data ────────────────────────────────────────────────────────
HOME = _env_path("DICTATION_HOME", "~/.local/share/dictation")
HISTORY_FILE = HOME / "history.jsonl"
LOG_FILE = Path(os.environ.get("DICTATION_LOG", "/tmp/dictation.log"))
STATE_FILE = Path(os.environ.get("DICTATION_STATE", "/tmp/dictation-state"))

# Generated artifacts. Both are derived from the corpus and must NOT be
# committed — they are a compact map of your internal vocabulary.
VOCAB_INDEX_FILE = HOME / "vocab_index.json"      # structured, for correction
VOCAB_PROMPT_FILE = HOME / "vocab_prompt.txt"     # flat string, for whisper --prompt

# ── corpus ──────────────────────────────────────────────────────────────────
# Where the vocabulary is derived from. Colon-separated roots; each is walked
# for the globs below. Point this at a docs repo, a wiki export, a service
# catalogue dump — anything with your proper nouns in it.
CORPUS_ROOTS = [
    Path(p).expanduser()
    for p in os.environ.get("DICTATION_CORPUS", "").split(":")
    if p.strip()
]
CORPUS_GLOBS = os.environ.get("DICTATION_CORPUS_GLOBS", "**/*.md:**/*.txt").split(":")

# ── behaviour ───────────────────────────────────────────────────────────────
MIC = os.environ.get("DICTATION_MIC", "MacBook Pro Microphone")
MIN_CLIP_SECONDS = float(os.environ.get("DICTATION_MIN_CLIP", "0.3"))
VOCAB_PROMPT_TERMS = int(os.environ.get("DICTATION_VOCAB_TERMS", "120"))
CORRECTION_ENABLED = os.environ.get("DICTATION_CORRECT", "1") not in ("0", "false", "no")

# System word list, used to decide whether a token is a real English word.
# Present on every macOS install; on Linux, install `words` / `wamerican`.
DICT_PATH = _env_path("DICTATION_DICT", "/usr/share/dict/words")


def ensure_home() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
