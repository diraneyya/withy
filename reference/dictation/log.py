"""Single-line append logging. Deliberately trivial — the point is that every
stage writes one, because almost every failure in this system is silent."""

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
    """Publish the current phase for a UI overlay to poll.

    States: recording | transcribing | injecting | idle. One writer per phase;
    whoever writes last owns what the user sees.
    """
    try:
        config.STATE_FILE.write_text(state)
    except OSError:
        pass
