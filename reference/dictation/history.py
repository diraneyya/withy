"""
history.py — append-only record of every dictation.

This is not a nice-to-have. Text injection fails in ordinary ways: the wrong
window had focus, the app swallowed the keystrokes, the user alt-tabbed mid-type.
Without a history the user has just lost a paragraph they spoke and cannot
reproduce. With one, recovery is `dictation history copy 1`.

Write to it BEFORE attempting injection, always.

Both `raw` and `final` are kept: `copy-raw` is the escape hatch when the
correction stage swapped a word wrongly, and the pair together is the evaluation
corpus you need to tell whether correction is helping.

Retention is a policy decision for a fleet deployment — this file contains, by
definition, everything the user has dictated. Default to a short window, exclude
it from backups and crash reports, and ship a purge command.
"""

from __future__ import annotations

import json
import time

from . import config


def append(raw: str, final: str, meta: dict) -> None:
    config.ensure_home()
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "raw": raw, "final": final, "meta": meta}
    with config.HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def recent() -> list[dict]:
    """Most-recent-first, so index 1 is the dictation just spoken."""
    if not config.HISTORY_FILE.exists():
        return []
    lines = config.HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    return list(reversed([json.loads(l) for l in lines if l.strip()]))


def purge(keep_days: int = 0) -> int:
    """Drop records older than `keep_days` (0 = drop everything). Returns the
    number removed."""
    recs = list(reversed(recent()))          # back to chronological
    if keep_days <= 0:
        kept: list[dict] = []
    else:
        cutoff = time.time() - keep_days * 86400
        kept = [r for r in recs
                if time.mktime(time.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")) >= cutoff]
    removed = len(recs) - len(kept)
    config.ensure_home()
    with config.HISTORY_FILE.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return removed
