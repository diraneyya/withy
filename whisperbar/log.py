"""Append-only logging and the UI state file.

Every stage writes a line, because almost every failure in a dictation pipeline
is silent: a zero-byte WAV, a dropped keystroke tail, a model that returned
nothing. The log is how any of that becomes visible.
"""

from __future__ import annotations

import time

from . import config


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
    try:
        with config.LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def set_state(state: str) -> None:
    """Publish the current phase so the menubar can render it.

    States: recording | transcribing | formatting | typing | idle
    """
    try:
        config.STATE_FILE.write_text(state)
    except OSError:
        pass
