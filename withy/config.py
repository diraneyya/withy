"""
config.py — paths, settings, and defaults.

Two directories, deliberately separate:

  ~/.config/withy/       things the USER edits (settings.json, vocabulary.txt)
  ~/.local/share/withy/  things the TOOL writes (history.jsonl, audio/)

Nothing is shared with any other tool on the machine. Withy can therefore
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

APP = "withy"


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name) or default).expanduser()


# Hammerspoon spawns processes with a minimal PATH that does NOT include
# /opt/homebrew/bin. Resolving tools through PATH alone therefore works from a
# shell and fails from the menubar — which is the whole product. Search the
# standard locations explicitly.
_SEARCH_DIRS = (os.path.expanduser("~/.local/bin"),
                "/opt/homebrew/bin", "/usr/local/bin", "/opt/homebrew/sbin",
                "/usr/bin", "/bin", "/usr/sbin", "/sbin")


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for d in _SEARCH_DIRS:
        for n in names:
            c = os.path.join(d, n)
            if os.access(c, os.X_OK):
                return c
    return None


def usable(path: str | None) -> bool:
    """Is this an actual executable, rather than a bare name we never resolved?

    `_which` falls back to the plain name so error messages stay readable, but a
    bare name is exactly what blows up under a minimal PATH — so anything that
    REPORTS on the install has to check this, not merely that the string is
    non-empty.
    """
    return bool(path) and os.path.isabs(path) and os.access(path, os.X_OK)


# ── directories ─────────────────────────────────────────────────────────────
CONFIG_DIR = _env_path("WITHY_CONFIG_DIR", f"~/.config/{APP}")
DATA_DIR = _env_path("WITHY_DATA_DIR", f"~/.local/share/{APP}")

SETTINGS_FILE = CONFIG_DIR / "settings.json"
VOCAB_FILE = CONFIG_DIR / "vocabulary.txt"
PROMPT_FILE = CONFIG_DIR / "prompt.md"
HISTORY_FILE = DATA_DIR / "history.jsonl"
AUDIO_DIR = DATA_DIR / "audio"

LOG_FILE = Path(os.environ.get("WITHY_LOG", f"/tmp/{APP}.log"))
STATE_FILE = Path(os.environ.get("WITHY_STATE", f"/tmp/{APP}-state"))
PID_FILE = Path(f"/tmp/{APP}-ffmpeg.pid")
CURRENT_WAV = Path(f"/tmp/{APP}-input.wav")

# ── binaries ────────────────────────────────────────────────────────────────
WHISPER_BIN = os.environ.get("WITHY_WHISPER_BIN") or _which("whisper-cli", "whisper-cpp") or "whisper-cli"
FFMPEG_BIN = os.environ.get("WITHY_FFMPEG_BIN") or _which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = os.environ.get("WITHY_FFPROBE_BIN") or _which("ffprobe") or "ffprobe"
OLLAMA_BIN = os.environ.get("WITHY_OLLAMA_BIN") or _which("ollama") or "ollama"

# ── defaults ────────────────────────────────────────────────────────────────
# record_key defaults to right-Option rather than fn, because fn is the key an
# incumbent dictation tool (Apple Dictation, Willow, Wispr Flow) most likely
# already owns. The menubar picker is how you move to fn once it is free.
DEFAULTS: dict = {
    "record_key": "rightalt",
    "whisper_model": "/opt/homebrew/share/whisper-cpp/ggml-large-v3-turbo.bin",
    "language": "auto",
    "mic": "default",
    # Filled in automatically the first time a device is chosen, so the
    # recording path never pays for enumeration.
    "resolved_mic": "",
    "postprocess": True,
    "llm_model": "qwen2.5:3b",
    # "local" keeps everything on the machine. "openai" sends the transcript to
    # a hosted model — faster and better, but it is the one thing that leaves.
    "polish_backend": "local",
    "openai_model": "gpt-4.1-mini",
    # Polishing runs on EVERY utterance, so the model is a recurring cost and a
    # latency floor, not a one-off. Both hosted defaults are the fast, cheap
    # tier of their family; raise them here if the quality does not hold.
    "anthropic_model": "claude-haiku-4-5",
    # Explicit argv for the "command" backend; empty = auto-detect
    # (claude, then aifx agent run claude, then llm).
    "polish_command": [],
    # Override the per-backend default chunk size; 0 = use the default.
    "chunk_words": 0,
    "llm_timeout": 25,   # a stalled model must not hold up typing
    "min_clip_seconds": 0.3,
    # dB between loud and quiet frames below which a take is treated as having
    # no speech in it. See speech.py for how this number was chosen.
    "speech_spread_db": 13.0,
    "keep_audio_days": 7,
    "sound": True,
    # Front-end preferences, written by the Hammerspoon menu; listed here so
    # `withy settings` can read and set them too.
    "banner": True,
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
    if os.environ.get("WITHY_MODEL"):
        s["whisper_model"] = os.environ["WITHY_MODEL"]
    if os.environ.get("WITHY_LLM_MODEL"):
        s["llm_model"] = os.environ["WITHY_LLM_MODEL"]
    if os.environ.get("WITHY_POSTPROCESS"):
        s["postprocess"] = os.environ["WITHY_POSTPROCESS"] not in ("0", "false", "no")
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
