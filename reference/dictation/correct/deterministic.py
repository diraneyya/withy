"""
deterministic.py — filler/stutter removal and whisper-loop collapse. No model.

This is a closed, rule-based problem, and pure code does it perfectly: it can
ONLY remove tokens on a fixed list or exact adjacent duplicates, so it can never
touch a content word or a proper noun.

That property was earned. A 1.5b local model asked to do the same job deleted a
company name, an insurance provider, half a model number, and the word "and" —
because a "deletions only" guardrail bounds a model from above (can't invent) but
not from below (can over-delete). See docs/03-correction.md.
"""

from __future__ import annotations

import re

# Single-token fillers. Conservative on purpose. Note "like" is EXCLUDED:
# "is like 1.8" (filler) vs "i like this" (verb) cannot be told apart by a token
# rule, so it is left for a context-aware pass rather than risking damage.
FILLERS = {
    "um", "umm", "uhm", "uh", "eh", "er", "erm", "uhh", "ahh", "hmm", "mm", "mhm",
}

# Multi-word hedges safe to drop wholesale (rare false positives).
MULTIWORD_FILLERS = [
    r"\byou know\b",
    r"\bi mean\b",
    r"\bsort of\b",
    r"\bkind of\b",
]


def _ntok(t: str) -> str:
    return re.sub(r"[^\w']", "", t).lower()


def collapse_phrase_repeats(tokens: list[str], removed: list[str],
                            max_unit: int = 10) -> list[str]:
    """Collapse an immediately-repeated multi-word phrase to a single copy.

    Second line of defence against whisper.cpp decode loops (`-mc 0` is the
    first). Comparison is on normalised tokens, but the ORIGINAL first
    occurrence survives with its capitalisation and punctuation intact.

    Conservative trigger — only collapse when it is almost certainly an
    artifact and not ordinary speech:
      - any unit repeated >= 3 times (a loop), or
      - a unit of >= 3 words repeated back-to-back (a verbatim echo).
    A 2-word phrase repeated exactly twice is left alone. "No, no" is a thing
    people say.
    """
    norms = [_ntok(t) for t in tokens]
    out: list[str] = []
    i, n = 0, len(tokens)
    while i < n:
        collapsed = False
        hi = min(max_unit, (n - i) // 2)
        for k in range(hi, 1, -1):
            unit = norms[i:i + k]
            if "" in unit:                       # punctuation-only token → skip
                continue
            reps, j = 1, i + k
            while norms[j:j + k] == unit:
                reps += 1
                j += k
            if reps >= 3 or (reps >= 2 and k >= 3):
                out.extend(tokens[i:i + k])       # keep the first occurrence verbatim
                removed.extend(tokens[i + k:j])   # drop the echoes
                i = j
                collapsed = True
                break
        if not collapsed:
            out.append(tokens[i])
            i += 1
    return out


def deterministic_clean(text: str) -> tuple[str, list[str]]:
    """Remove fixed fillers and immediate stutters, then collapse loops.

    Returns (cleaned_text, removed_tokens). The removed list is kept so the
    history record can show what was dropped.
    """
    removed: list[str] = []

    # 1) multi-word hedges
    for pat in MULTIWORD_FILLERS:
        def _rec(m, _removed=removed):
            _removed.append(m.group(0))
            return " "
        text = re.sub(pat, _rec, text, flags=re.IGNORECASE)

    # 2) token pass: drop single-token fillers, collapse adjacent duplicates
    out: list[str] = []
    for tok in text.split():
        bare = re.sub(r"[^\w']", "", tok).lower()
        if bare in FILLERS:
            removed.append(tok)
            continue
        if out and re.sub(r"[^\w']", "", out[-1]).lower() == bare and bare:
            removed.append(tok)                   # "the the" → "the"
            continue
        out.append(tok)

    # 3) collapse immediately-repeated multi-word phrases
    out = collapse_phrase_repeats(out, removed)

    return re.sub(r"\s+", " ", " ".join(out)).strip(), removed
