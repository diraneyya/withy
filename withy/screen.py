"""
screen.py — terms read off the screen, as momentary context for whisper.

EXPERIMENT (2026-09-29). Whisper's `--prompt` biases which words it hears. The
static vocabulary file is one source of such words; this is a second, read at
the moment of dictation: the visible text of the element you are dictating
into (a terminal's visible lines, a text field's contents), via the macOS
Accessibility interface Hammerspoon already holds.

Three rules, each load-bearing:
  - Only text Withy did NOT type counts. Everything Withy typed is on the
    screen afterwards; learning from it would feed whisper's own guesses back.
    Recent history finals are removed from the screen text before extracting.
  - Only non-dictionary words with a capital letter or a digit are candidates
    (YubiKey, OrwaTech, LXC, gpt-image-2). Lowercase non-words are mostly typos.
  - The terms go to WHISPER ONLY. They never join the vocabulary list sent to a
    polishing backend, which may be hosted.

Nothing is stored between dictations: this is momentary context only.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import config, history
from .log import log

_LUA = r'''
local ax = require("hs.axuielement")
-- Withy types into the frontmost app, so during a dictation that app IS the
-- target. If Hammerspoon itself is in front (its menu or console is open),
-- skip: listing every window to find the one below takes seconds.
local app = hs.application.frontmostApplication()
if app and app:bundleID() == "org.hammerspoon.Hammerspoon" then app = nil end
local el = app and ax.applicationElement(app):attributeValue("AXFocusedUIElement")
local how, txt = "none", ""
if el then
  local r = el:attributeValue("AXVisibleCharacterRange")
  if r and r.length > 0 then
    txt = el:parameterizedAttributeValue("AXStringForRange", r) or ""; how = "visible"
  else
    local v = el:attributeValue("AXValue")
    if type(v) == "string" then txt = v:sub(-20000); how = "value" end
  end
end
local f = io.open(WITHY_OUT, "w"); f:write(txt); f:close()
return (app and app:name() or "?") .. "\t" .. how
'''

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-']*[A-Za-z0-9]")
_DICT = Path("/usr/share/dict/words")
MAX_TERMS = 60


@lru_cache(maxsize=1)
def _dictionary() -> frozenset[str]:
    try:
        return frozenset(w.strip().lower() for w in _DICT.read_text().splitlines())
    except OSError:
        return frozenset()


def _in_dictionary(word: str) -> bool:
    d = _dictionary()
    w = word.lower().replace("'", "")
    if w in d:
        return True
    stems = {w}
    for pre in ("re", "un", "pre", "non", "over", "sub"):
        if w.startswith(pre) and len(w) > len(pre) + 2:
            stems.add(w[len(pre):])
    for s in list(stems):
        if s in d:
            return True
        for suf in ("s", "es", "ed", "ing", "er", "ers", "ly"):
            if s.endswith(suf):
                base = s[: -len(suf)]
                # running -> run, philosophizing -> philosophize
                if base in d or base + "e" in d or (
                        len(base) > 2 and base[-1] == base[-2] and base[:-1] in d):
                    return True
    return False


def read_focused() -> tuple[str, str, str]:
    """(app name, how it was read, text). ('', 'failed', '') on any failure."""
    out = config.DATA_DIR / "screen.txt"
    lua = config.DATA_DIR / "screen.lua"
    try:
        lua.write_text(_LUA)
        out.unlink(missing_ok=True)
        from .inject import HS_BIN
        res = subprocess.run(
            [HS_BIN or "hs", "-q", "-t", "2",
             "-c", f"WITHY_OUT={str(out)!r}; return dofile({str(lua)!r})"],
            capture_output=True, text=True, timeout=4,
            stdin=subprocess.DEVNULL)
        app, _, how = res.stdout.strip().rpartition("\n")[-1].partition("\t")
        return app, how, out.read_text(errors="replace") if out.exists() else ""
    except (OSError, subprocess.SubprocessError) as e:
        log(f"screen: read failed: {e}")
        return "", "failed", ""


def _norm(s: str) -> str:
    return " ".join(s.split())


def extract_terms(text: str, typed: list[str], known: list[str]) -> list[str]:
    """Candidate terms from `text`, after removing everything Withy typed."""
    text = _norm(text)
    for t in sorted({_norm(x) for x in typed if len(x.split()) >= 3}, key=len, reverse=True):
        text = text.replace(t, " ")
    seen_known = {k.lower() for k in known}
    counts: Counter[str] = Counter()
    for w in _WORD_RE.findall(text):
        w = re.sub(r"'s$", "", w)
        # contractions, measurements and file names are not terms
        if "'" in w or "." in w or w[0].isdigit():
            continue
        if not (3 <= len(w) <= 30):
            continue
        if not any(c.isupper() or c.isdigit() for c in w) or w.isdigit():
            continue
        if not any(c.isalpha() for c in w) or w.lower() in seen_known:
            continue
        if _in_dictionary(w):
            continue
        counts[w] += 1
    return [w for w, _ in counts.most_common(MAX_TERMS)]


def context() -> dict:
    """Read the screen and return {'app', 'how', 'chars', 'terms'}."""
    app, how, text = read_focused()
    typed = [r.get("final", "") for r in history.recent(50)]
    from . import vocab
    terms = extract_terms(text, typed, vocab.load()) if text else []
    return {"app": app, "how": how, "chars": len(text), "terms": terms}
