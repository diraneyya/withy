"""
match.py — PRECISION-FIRST proper-noun correction against the corpus index.

History, because it determines the whole shape of this file. The first version
maximised recall: phonetically compare every 1-3 token span to every index entry.
On a 3,475-entry index it produced 65 swaps, 49 ambiguous, and destroyed a clean
control sentence. Against a generic infrastructure vocabulary the same collisions
reproduce exactly: need→Node and note→Node (both NT), docs→DAGs (TKS),
apps→APIs (APS), reads→Redis (RTS), stacks→SDKs (STKS).

The reason is not tunable. At that index size almost any short span shares an
exact metaphone with SOME term, and string similarity cannot separate the good
match from the bad one: `need↔Node` and `graphana↔Grafana` are both exact
metaphone matches with comparable edit distance. The only discriminator is that
"need" is a real English word and "graphana" is not.

So: gate on out-of-vocabulary, and accept only EXACT matches. A false correction
corrupts silently and may survive review; a miss is visible and the user fixes it
in one keystroke. Precision >> recall for a corrector.

Three narrow rules, each high-precision:
  1) concat-exact   join 2-3 adjacent tokens; swap iff the joined form EXACTLY
                    equals a corpus term (spacing garbles: pager duty →
                    PagerDuty, data dog → Datadog, terra form → Terraform)
  2) spoken-letter  a run of letter-name tokens → acronym, accepted iff it
                    exactly matches a corpus term (ess ell oh → SLO, ay pee eye → API)
  3) oov-metaphone  a SINGLE token that is NOT a dictionary word, not already a
                    corpus term, with an EXACT metaphone match (graphana → Grafana)

Real-word multi-token garbles (easy two → EC2, cube control → kubectl) are
deliberately NOT handled — their tokens are valid words, so no deterministic gate
can flag them. This module's standing contract: NEVER fire on an ordinary word.
"""

from __future__ import annotations

import re

import jellyfish as jf

from .. import config
from .vocab import norm as _norm

MIN_FREQ = 4          # corpus terms rarer than this are noise
MIN_TARGET_LEN = 4    # shorter targets are too collision-prone

LETTER = {
    "ay": "a", "bee": "b", "be": "b", "cee": "c", "see": "c", "sea": "c",
    "dee": "d", "ee": "e", "ef": "f", "eff": "f", "gee": "g", "jee": "g",
    "aitch": "h", "haitch": "h", "aytch": "h", "eye": "i", "jay": "j",
    "kay": "k", "el": "l", "ell": "l", "em": "m", "en": "n", "oh": "o",
    "pee": "p", "pea": "p", "cue": "q", "queue": "q", "ar": "r", "are": "r",
    "es": "s", "ess": "s", "tee": "t", "tea": "t", "yew": "u", "vee": "v",
    "ve": "v", "doubleu": "w", "ex": "x", "why": "y", "zee": "z", "zed": "z",
    "zet": "z",
}

# Genuine contractions to leave alone. A possessive on a NON-word stem
# (whisper's "Kubernetti's" for Kubernetes) is deliberately NOT here, so it
# stays correctable — see _bare().
CONTRACTIONS = {
    "what's", "i'm", "don't", "can't", "won't", "i've", "you're", "they're",
    "i'd", "i'll", "he's", "she's", "it's", "let's", "that's", "we've",
    "you've", "there's", "we're", "who's", "wouldn't", "couldn't", "shouldn't",
    "didn't", "doesn't", "isn't", "aren't", "wasn't", "weren't", "haven't",
    "hasn't", "hadn't", "you'll", "he'll", "she'll", "they'll", "we'll",
    "they've", "you'd", "he'd", "she'd", "they'd", "what're", "how's",
}


def _load_dict() -> set[str]:
    words: set[str] = set()
    p = config.DICT_PATH
    if p and p.exists():
        for line in p.read_text(errors="ignore").splitlines():
            w = line.strip().lower()
            if w:
                words.add(w)
    return words


ENGLISH = _load_dict()


def _bare(tok: str) -> str:
    """Match surface: lowercase, strip to [a-z0-9]. Apostrophes are DROPPED,
    not split on, so a possessive collapses to stem+s: "Kubernetti's" → "kubernettis"
    (→ metaphone KBRNTS → Kubernetes). Splitting instead is how the first version
    skipped exactly the garbles it existed to fix."""
    return re.sub(r"[^a-z0-9]", "", tok.lower())


def _deinflect(bare: str) -> set[str]:
    """Candidate base forms of a possibly-inflected token.

    /usr/share/dict/words holds base lemmas and is missing most plurals,
    possessives, and verb inflections — so "docs", "apps", "reads", "tags"
    all looked out-of-vocabulary and became eligible for a phonetic swap
    (docs→DAGs, apps→APIs, reads→Redis). Reducing to a lemma and re-checking
    the dictionary closes that hole. Genuine garbles (graphana, kubernetis) do not
    reduce to a dictionary word, so they stay correctable.
    """
    c: set[str] = set()
    b = bare
    if len(b) > 3 and b.endswith("s"):
        c.add(b[:-1])                       # docs→doc, apps→app, reads→read
        if len(b) > 4 and b.endswith("es"):
            c.add(b[:-2])                   # boxes→box
            if b.endswith("ies"):
                c.add(b[:-3] + "y")         # parties→party
    if len(b) > 4 and b.endswith("ed"):
        c.add(b[:-1])                       # liked→like
        c.add(b[:-2])                       # walked→walk
        if b.endswith("ied"):
            c.add(b[:-3] + "y")             # tried→try
    if len(b) > 5 and b.endswith("ing"):
        c.add(b[:-3])                       # walking→walk
        c.add(b[:-3] + "e")                 # making→make
    return c


def _is_common_word(tok: str) -> bool:
    """True if this is an ordinary word we must NOT touch."""
    low = tok.strip().lower().strip('.,!?;:"()[]')
    if low in CONTRACTIONS:
        return True
    bare = _bare(tok)
    if not bare or bare.isdigit():
        return True
    if bare in ENGLISH:
        return True
    return any(c in ENGLISH for c in _deinflect(bare))


def _by_norm(index: list[dict]) -> dict[str, dict]:
    d: dict[str, dict] = {}
    for e in index:
        cur = d.get(e["norm"])
        if cur is None or e["freq"] > cur["freq"]:
            d[e["norm"]] = e
    return d


def find_matches(text: str, index: list[dict]) -> list[dict]:
    toks = text.split()
    n = len(toks)
    by_norm = _by_norm(index)
    proposals: list[dict] = []

    # Rule 1 — concat-exact: joined tokens exactly equal a corpus term.
    for w in (3, 2):
        for i in range(n - w + 1):
            span = toks[i:i + w]
            joined = _norm("".join(_bare(t) for t in span))
            if len(joined) < 5:
                continue
            e = by_norm.get(joined)
            if e and e["freq"] >= MIN_FREQ:
                proposals.append({
                    "start": i, "end": i + w, "span": " ".join(span),
                    "canonical": e["canonical"], "id": e["id"],
                    "method": "concat-exact",
                })

    # Rule 2 — spoken-letter runs expand to an acronym present in the index.
    for w in (4, 3, 2):
        for i in range(n - w + 1):
            span = toks[i:i + w]
            letters = [LETTER.get(_bare(t)) for t in span]
            if any(l is None for l in letters):
                continue
            e = by_norm.get("".join(letters))
            if e:
                proposals.append({
                    "start": i, "end": i + w, "span": " ".join(span),
                    "canonical": e["canonical"], "id": e["id"],
                    "method": "spoken-letter",
                })

    # Rule 3 — single out-of-vocabulary token with an exact metaphone match.
    for i, tok in enumerate(toks):
        bare = _bare(tok)
        if len(bare) < MIN_TARGET_LEN:
            continue
        if _is_common_word(tok):     # raw token, so the contraction check sees the apostrophe
            continue
        if bare in by_norm:          # already correct → no-op
            continue
        tmeta = jf.metaphone(bare)
        if not tmeta:
            continue
        hits = [e for e in index
                if e["freq"] >= MIN_FREQ
                and len(e["norm"]) >= MIN_TARGET_LEN
                and e["meta"] == tmeta
                and e["norm"] != bare
                and not _is_common_word(e["norm"])]
        if not hits:
            continue
        hits.sort(key=lambda e: -e["freq"])
        proposals.append({
            "start": i, "end": i + 1, "span": tok,
            "canonical": hits[0]["canonical"], "id": hits[0]["id"],
            "method": "oov-metaphone",
            "alts": [{"id": h["id"], "canonical": h["canonical"], "freq": h["freq"]}
                     for h in hits[:4]],
        })

    # Greedy, non-overlapping: longer spans first, exact rules before phonetic.
    rank = {"concat-exact": 0, "spoken-letter": 0, "oov-metaphone": 1}
    proposals.sort(key=lambda p: (-(p["end"] - p["start"]), rank[p["method"]]))
    chosen, used = [], set()
    for p in proposals:
        rng = set(range(p["start"], p["end"]))
        if rng & used:
            continue
        used |= rng
        chosen.append(p)
    chosen.sort(key=lambda p: p["start"])
    return chosen


def apply_matches(text: str, matches: list[dict]) -> str:
    toks = text.split()
    for p in sorted(matches, key=lambda p: -p["start"]):
        toks[p["start"]:p["end"]] = [p["canonical"]]
    return " ".join(toks)
