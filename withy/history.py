"""
history.py — append-only record of every dictation.

This is not a nice-to-have; it is the recovery path. Injection fails in ordinary
ways: the wrong window had focus, the app swallowed the keystrokes, the user
alt-tabbed mid-type. Without a history the user has lost a paragraph they spoke
and cannot reproduce. With one, it is two clicks in the menubar.

Write BEFORE attempting injection, always.

Three versions of the text are kept — `raw` (what was heard), `corrected`
(after the deterministic stage) and `final` (after formatting) — because when a
stage gets something wrong, the user wants the version from before it ran, and
because the three together are the evaluation corpus for whether any of this is
actually helping.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import config


def append(raw: str, corrected: str, final: str, meta: dict,
           wav: Path | None = None) -> dict:
    config.ensure_dirs()
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "raw": raw, "corrected": corrected, "final": final, "meta": meta}
    if wav is not None:
        rec["wav"] = str(wav)
    with config.HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def recent(limit: int = 0) -> list[dict]:
    """Most-recent-first, so index 0 is the dictation just spoken."""
    if not config.HISTORY_FILE.exists():
        return []
    out = []
    for line in config.HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    out.reverse()
    return out[:limit] if limit else out


def purge(keep_days: int = 0) -> int:
    recs = list(reversed(recent()))
    if keep_days <= 0:
        kept: list[dict] = []
    else:
        cutoff = time.time() - keep_days * 86400
        kept = [r for r in recs
                if time.mktime(time.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")) >= cutoff]
    removed = len(recs) - len(kept)
    config.ensure_dirs()
    with config.HISTORY_FILE.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return removed
