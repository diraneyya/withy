"""
correct.py — the deterministic stage. Small on purpose.

This module is what survived measurement. Each rule below was checked against
360 real dictations; anything whose failures outnumbered its successes was
removed rather than tuned.

KEPT
  concat-exact     join 2-3 adjacent tokens and swap only when the joined form
                   EXACTLY matches a vocabulary term (second brain →
                   SecondBrain, pager duty → PagerDuty). ~27 firings, 4 bad.
  spoken-letter    a run of letter-names whose expansion exactly matches a
                   vocabulary term (pee aitch → pH, ess ell oh → SLO).
  fillers          a fixed, short list of single tokens (um, uh, erm).
  loop guard       collapse a phrase repeated 3+ times — the signature of a
                   whisper.cpp decoding loop, not of human speech.

REMOVED, and why — these are not to be reinstated without new measurement:
  oov-metaphone    "a single out-of-vocabulary token with an exact metaphone
                   match". 24 firings, 15 of which damaged the text: gonna →
                   Kuhn, died → T8DE84EW, cues → Gaza, badass → Bytes. The
                   phonetic key is simply too coarse: metaphone("badass") ==
                   metaphone("Bytes") == "BTS". Garbled proper nouns are now
                   handled by the post-processing model, which has the sentence
                   around the word and can tell "a node" from "Anode".
  sort of/kind of  deleted as hedges. Of 20 firings sampled, every single one
                   was a legitimate use ("what KIND OF proof is needed", "the
                   SORT OF thing that deserves publishing"). These almost always
                   introduce a noun of type, not a hedge.
  "I mean"         same failure ("I mean it", "I mean business").

When post-processing is enabled the model does all disfluency work, and this
module runs vocabulary rules only — see `clean()`.
"""

from __future__ import annotations

import re

from .vocab import by_norm, norm

FILLERS = {
    "um", "umm", "uhm", "uh", "uhh", "eh", "er", "erm", "ahh", "hmm", "mm", "mhm",
}

# The only multi-word hedge safe to drop wholesale. "you know" is almost never
# a content phrase; every other candidate tested was.
MULTIWORD_FILLERS = [r"\byou know\b"]

LETTER = {
    "ay": "a", "bee": "b", "be": "b", "cee": "c", "see": "c", "sea": "c",
    "dee": "d", "ee": "e", "ef": "f", "eff": "f", "gee": "g", "jee": "g",
    "aitch": "h", "haitch": "h", "aytch": "h", "eye": "i", "jay": "j",
    "kay": "k", "el": "l", "ell": "l", "em": "m", "en": "n", "oh": "o",
    "pee": "p", "pea": "p", "cue": "q", "queue": "q", "ar": "r", "are": "r",
    "es": "s", "ess": "s", "tee": "t", "tea": "t", "yew": "u", "vee": "v",
    "ve": "v", "doubleu": "w", "ex": "x", "why": "y", "zee": "z", "zed": "z",
}


def _bare(tok: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def collapse_loops(tokens: list[str], removed: list[str], max_unit: int = 10) -> list[str]:
    """Collapse a phrase repeated 3+ times consecutively.

    whisper.cpp can fall into a decoding loop where a confidently-wrong token
    feeds itself forward; a six-word phrase emitted 56 times is the recorded
    worst case. `-mc 0` at transcribe time reduces this but does not eliminate
    it, so this is the second line of defence.

    The trigger is 3+ repetitions ONLY. An earlier version also collapsed any
    3-word phrase repeated twice, which is ordinary speech ("no no no" is a
    loop; "I said it, I said it" is a person).
    """
    norms = [_bare(t) for t in tokens]
    out: list[str] = []
    i, n = 0, len(tokens)
    while i < n:
        collapsed = False
        for k in range(min(max_unit, (n - i) // 3), 0, -1):
            unit = norms[i:i + k]
            if not unit or "" in unit:
                continue
            reps, j = 1, i + k
            while norms[j:j + k] == unit:
                reps += 1
                j += k
            if reps >= 3:
                out.extend(tokens[i:i + k])      # keep the first occurrence verbatim
                removed.extend(tokens[i + k:j])
                i = j
                collapsed = True
                break
        if not collapsed:
            out.append(tokens[i])
            i += 1
    return out


def apply_vocabulary(text: str, terms: list[str]) -> tuple[str, list[dict]]:
    """concat-exact and spoken-letter, non-overlapping, longest span first."""
    if not terms:
        return text, []
    index = by_norm(terms)
    toks = text.split()
    n = len(toks)
    proposals: list[dict] = []

    # concat-exact — spacing garbles. Requires an EXACT match of the joined
    # form; "page duty" stays untouched because "pageduty" is not a term.
    for w in (3, 2):
        for i in range(n - w + 1):
            span = toks[i:i + w]
            joined = "".join(_bare(t) for t in span)
            if len(joined) < 5:
                continue
            canon = index.get(joined)
            # Skip when the tokens are already the term (no-op) or when the
            # span already spells it correctly with a space the user wanted.
            # canon's normalised form IS `joined`, so any match here differs
            # from what was spoken only by spacing/case — which is the garble
            # this rule exists to fix.
            if canon and " ".join(span) != canon:
                proposals.append({"start": i, "end": i + w, "span": " ".join(span),
                                  "to": canon, "method": "concat-exact"})

    # spoken-letter — "pee aitch" → pH, accepted only if the expansion is a term.
    for w in (5, 4, 3, 2):
        for i in range(n - w + 1):
            span = toks[i:i + w]
            letters = [LETTER.get(_bare(t)) for t in span]
            if any(l is None for l in letters):
                continue
            canon = index.get("".join(letters))
            if canon:
                proposals.append({"start": i, "end": i + w, "span": " ".join(span),
                                  "to": canon, "method": "spoken-letter"})

    proposals.sort(key=lambda p: -(p["end"] - p["start"]))
    chosen, used = [], set()
    for p in proposals:
        rng = set(range(p["start"], p["end"]))
        if rng & used:
            continue
        used |= rng
        chosen.append(p)
    chosen.sort(key=lambda p: p["start"])

    # Re-attach trailing punctuation the span carried, so a swap can never eat
    # a sentence boundary (an earlier version turned "badass. Okay?" into
    # "Bytes Okay?" by swallowing the full stop).
    for p in sorted(chosen, key=lambda p: -p["start"]):
        tail = re.search(r"[^\w\s]+$", toks[p["end"] - 1])
        toks[p["start"]:p["end"]] = [p["to"] + (tail.group(0) if tail else "")]
    return " ".join(toks), chosen


def clean(text: str, terms: list[str], disfluency: bool = True) -> tuple[str, dict]:
    """Deterministic pass.

    `disfluency=False` when a post-processing model will run afterwards: the
    model removes fillers and stutters with the context to do it correctly, so
    doing it here first only risks damage it cannot undo. The loop guard still
    runs either way — a 56x repetition is a decoding artifact, and feeding it to
    a small model is asking for trouble.
    """
    removed: list[str] = []

    # "um"/"uh" are never content, in any context. They are removed even when
    # the model will run, because it treats them as words to punctuate around
    # ("um, so I was thinking") rather than noise to drop.
    if disfluency:
        for pat in MULTIWORD_FILLERS:
            def _rec(m, _r=removed):
                _r.append(m.group(0))
                return " "
            text = re.sub(pat, _rec, text, flags=re.IGNORECASE)

    out: list[str] = []
    for tok in text.split():
        bare = _bare(tok)
        if bare in FILLERS:                                   # always
            removed.append(tok)
            continue
        if disfluency and out and _bare(out[-1]) == bare and bare:   # "the the"
            removed.append(tok)
            continue
        out.append(tok)
    tokens = out

    tokens = collapse_loops(tokens, removed)
    text = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    text, swaps = apply_vocabulary(text, terms)
    return text, {"removed": removed, "swaps": swaps}
