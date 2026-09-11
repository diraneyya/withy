"""
config.py — paths, settings, and defaults.

Two directories, deliberately separate:

  ~/.config/whisperbar/       things the USER edits (settings.json, vocabulary.txt)
  ~/.local/share/whisperbar/  things the TOOL writes (history.jsonl, audio/)

Nothing is shared with any other tool on the machine. Whisperbar can therefore
be installed alongside an existing dictation setup — including another
Hammerspoon-based one — without either knowing the other exists.

Every setting is also overridable by environment variable, which is what makes
the pipeline testable offline without touching the user's real configuration.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

APP = "whisperbar"


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name) or default).expanduser()


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


# ── directories ─────────────────────────────────────────────────────────────
CONFIG_DIR = _env_path("WHISPERBAR_CONFIG_DIR", f"~/.config/{APP}")
DATA_DIR = _env_path("WHISPERBAR_DATA_DIR", f"~/.local/share/{APP}")

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VOCAB_FILE = CONFIG_DIR / "vocabulary.txt"
HISTORY_FILE = DATA_DIR / "history.jsonl"
AUDIO_DIR = DATA_DIR / "audio"

LOG_FILE = Path(os.environ.get("WHISPERBAR_LOG", f"/tmp/{APP}.log"))
STATE_FILE = Path(os.environ.get("WHISPERBAR_STATE", f"/tmp/{APP}-state"))
PID_FILE = Path(f"/tmp/{APP}-ffmpeg.pid")
CURRENT_WAV = Path(f"/tmp/{APP}-input.wav")

# ── binaries ────────────────────────────────────────────────────────────────
WHISPER_BIN = os.environ.get("WHISPERBAR_WHISPER_BIN") or _which("whisper-cli", "whisper-cpp") or "whisper-cli"
FFMPEG_BIN = os.environ.get("WHISPERBAR_FFMPEG_BIN") or _which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = os.environ.get("WHISPERBAR_FFPROBE_BIN") or _which("ffprobe") or "ffprobe"
OLLAMA_BIN = os.environ.get("WHISPERBAR_OLLAMA_BIN") or _which("ollama") or "ollama"

# ── defaults ────────────────────────────────────────────────────────────────
# record_key defaults to right-Option rather than fn, because fn is the key an
# incumbent dictation tool (Apple Dictation, Willow, Wispr Flow) most likely
# already owns. The menubar picker is how you move to fn once it is free.
DEFAULTS: dict = {
    "record_key": "rightalt",
    "whisper_model": "/opt/homebrew/share/whisper-cpp/ggml-large-v3-turbo.bin",
    "language": "auto",
    "mic": "default",
    "postprocess": True,
    "llm_model": "qwen2.5:3b",
    "llm_timeout": 25,   # a stalled model must not hold up typing
    "min_clip_seconds": 0.3,
    "keep_audio_days": 7,
    "sound": True,
    # Absolute path to the launcher. Written by install.sh and read by the
    # Hammerspoon front end, which is spawned with a minimal environment and
    # therefore cannot rely on PATH.
    "cli_path": "",
}

_cache: dict | None = None


def settings(reload: bool = False) -> dict:
    """User settings merged over DEFAULTS. Unknown keys are preserved."""
    global _cache
    if _cache is not None and not reload:
        return _cache
    s = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass  # a corrupt settings file must never stop dictation working
    # Environment overrides win over the file — this is the offline-test path.
    if os.environ.get("WHISPERBAR_MODEL"):
        s["whisper_model"] = os.environ["WHISPERBAR_MODEL"]
    if os.environ.get("WHISPERBAR_LLM_MODEL"):
        s["llm_model"] = os.environ["WHISPERBAR_LLM_MODEL"]
    if os.environ.get("WHISPERBAR_POSTPROCESS"):
        s["postprocess"] = os.environ["WHISPERBAR_POSTPROCESS"] not in ("0", "false", "no")
    _cache = s
    return s


def save_settings(updates: dict) -> dict:
    """Merge `updates` into settings.json and return the new settings."""
    ensure_dirs()
    cur = {}
    if SETTINGS_FILE.exists():
        try:
            cur = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cur = {}
    cur.update(updates)
    SETTINGS_FILE.write_text(json.dumps(cur, indent=2) + "\n", encoding="utf-8")
    return settings(reload=True)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
