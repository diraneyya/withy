"""
inject.py — put text into whatever application has focus (macOS).

Two paths, chosen by length:

  short (<= KEYSTROKE_MAX)   synthetic keystrokes. Unicode- and RTL-safe, and
                             it does NOT touch the clipboard.
  long                       clipboard paste (save -> set -> Cmd-V -> restore).
                             Atomic and length-independent.

The threshold is not arbitrary. Keystroke injection posts one event per
character, and on a long burst the receiving application drops the tail — a
3,267-character dictation arrived truncated with no error anywhere.

Hammerspoon is used when present because it is a persistent process, so the
clipboard restore can be scheduled and still run after our own exit. osascript
is the fallback and needs no dependency, but this process must stay alive for
the restore delay.

Text is passed to Hammerspoon through a FILE, never a shell argument — that
dodges every quoting pitfall at once: apostrophes, em-dashes, newlines, Arabic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .log import log

KEYSTROKE_MAX = 120
# PID-unique: two dictations can legitimately be in flight at once (a long take
# still transcribing while the next one finishes), and a shared temp file would
# let the second overwrite the first mid-read.
TYPE_TMP = Path(f"/tmp/withy-out-{os.getpid()}.txt")

HS_BIN = shutil.which("hs")


def _inject_hammerspoon(text: str) -> bool:
    TYPE_TMP.write_text(text, encoding="utf-8")
    read = f'local f=io.open([[{TYPE_TMP}]],"r");local t=f:read("a");f:close();'
    if len(text) <= KEYSTROKE_MAX:
        lua = read + "hs.eventtap.keyStrokes(t)"
    else:
        lua = read + (
            'local prev=hs.pasteboard.readString();'
            'hs.pasteboard.setContents(t);'
            'hs.eventtap.keyStroke({"cmd"},"v");'
            # Runs inside the persistent Hammerspoon process, so it fires even
            # though `hs -c` has already returned. If prev is nil the clipboard
            # held non-string data we could not capture — leave the dictation
            # there rather than destroying something we never read.
            'hs.timer.doAfter(0.5,function() '
            'if prev then hs.pasteboard.setContents(prev) end end)'
        )
    try:
        res = subprocess.run([HS_BIN, "-c", lua], capture_output=True,
                             text=True, timeout=120)
    finally:
        TYPE_TMP.unlink(missing_ok=True)
    if res.returncode != 0:
        log(f"inject(hs) FAILED rc={res.returncode}: {res.stderr[:200]}")
        return False
    return True


def _inject_osascript(text: str) -> bool:
    if len(text) <= KEYSTROKE_MAX:
        # AppleScript string literal: escape backslashes and quotes, only.
        esc = text.replace("\\", "\\\\").replace('"', '\\"')
        res = subprocess.run(
            ["osascript", "-e", f'tell application "System Events" to keystroke "{esc}"'],
            capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            log(f"inject(osascript) FAILED: {res.stderr[:200]}")
            return False
        return True

    prev = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    copy(text)
    res = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using {command down}'],
        capture_output=True, text=True, timeout=120)
    ok = res.returncode == 0
    if not ok:
        log(f"inject(osascript paste) FAILED: {res.stderr[:200]}")
    time.sleep(0.5)   # no persistent host here, so we hold open for the restore
    if prev:
        copy(prev)
    return ok


def copy(text: str) -> None:
    """Put text on the clipboard (used by the menubar's copy actions)."""
    subprocess.run(["pbcopy"], input=text.encode("utf-8"))


def inject(text: str) -> bool:
    """Insert `text` at the cursor. Returns False on failure — the caller must
    already have written it to history, so nothing is ever lost."""
    if not text:
        return False
    try:
        return _inject_hammerspoon(text) if HS_BIN else _inject_osascript(text)
    except Exception as e:                                   # noqa: BLE001
        log(f"inject raised: {type(e).__name__}: {e}")
        return False
