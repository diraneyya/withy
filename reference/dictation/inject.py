"""
inject.py — put the text into whatever application has focus (macOS).

Two paths, chosen by length:

  short (<= KEYSTROKE_MAX)  synthetic keystrokes. Unicode- and RTL-safe, and it
                            does NOT touch the clipboard.
  long                      clipboard paste (save → set → Cmd-V → restore).
                            Atomic and length-independent.

The threshold is not arbitrary. Synthetic keystroke injection posts one event per
character, and on a long burst the receiving application drops the tail — a
3,267-character dictation arrived truncated, with no error anywhere.

Two hosts are supported. Hammerspoon if present (a persistent process, so the
clipboard restore can be scheduled and survive our exit); otherwise plain
osascript, which needs no dependency but requires this process to stay alive for
the restore delay.

A cleaner approach exists and is not implemented here: write directly into the
focused element via the Accessibility API (AXUIElement / kAXSelectedTextAttribute).
No clipboard, no keystroke queue, no length limit — but inconsistent in Electron
and web views, which is where most dictation happens. Try it first in a native
implementation, fall back to paste.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .log import log

KEYSTROKE_MAX = 120
TYPE_TMP = Path("/tmp/dictation-out.txt")

HS_BIN = shutil.which("hs")


def _inject_hammerspoon(text: str) -> bool:
    """Text is passed through a FILE, never a shell argument — that dodges every
    quoting pitfall at once (apostrophes, em-dashes, Arabic, newlines)."""
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
    # Generous timeout: paste is instant, but a borderline-length keystroke run
    # genuinely takes seconds and a 30s cap can kill it mid-type.
    res = subprocess.run([HS_BIN, "-c", lua], capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        log(f"inject(hs) FAILED rc={res.returncode}: {res.stderr[:200]}")
        return False
    return True


def _osascript(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True, timeout=timeout)


def _inject_osascript(text: str) -> bool:
    if len(text) <= KEYSTROKE_MAX:
        # `keystroke` takes the text as an AppleScript string literal, so escape
        # backslashes and quotes — and only these. Never build it with printf %q.
        esc = text.replace("\\", "\\\\").replace('"', '\\"')
        res = _osascript(f'tell application "System Events" to keystroke "{esc}"')
        if res.returncode != 0:
            log(f"inject(osascript) FAILED: {res.stderr[:200]}")
            return False
        return True

    prev = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
    subprocess.run(["pbcopy"], input=text.encode("utf-8"))
    res = _osascript('tell application "System Events" to keystroke "v" using {command down}')
    ok = res.returncode == 0
    if not ok:
        log(f"inject(osascript paste) FAILED: {res.stderr[:200]}")
    # No persistent host here, so we hold the process open for the restore.
    time.sleep(0.5)
    if prev:
        subprocess.run(["pbcopy"], input=prev.encode("utf-8"))
    return ok


def inject(text: str) -> bool:
    """Insert `text` at the current cursor. Returns False on failure — the caller
    must have already written it to history, so nothing is ever lost."""
    if not text:
        return False
    try:
        return _inject_hammerspoon(text) if HS_BIN else _inject_osascript(text)
    except Exception as e:                                   # noqa: BLE001
        log(f"inject raised: {e}")
        return False
