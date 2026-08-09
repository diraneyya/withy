"""
The correction stage: deterministic, model-free, zero false positives.

    correct(text, lang) -> (final_text, meta)

Correction runs for ENGLISH ONLY. The matcher is built on an English dictionary
and English metaphone keys; run it over Arabic or Japanese tokens and it will
cheerfully "correct" them into English proper nouns. Non-English transcripts pass
through untouched.
"""

from __future__ import annotations

from .deterministic import deterministic_clean
from .match import apply_matches, find_matches
from .vocab import load_index

__all__ = ["correct", "deterministic_clean", "find_matches", "apply_matches", "load_index"]


def correct(text: str, lang: str = "en", index: list[dict] | None = None) -> tuple[str, dict]:
    if lang != "en":
        return text, {"lang": lang, "removed": [], "swaps": []}

    cleaned, removed = deterministic_clean(text)
    idx = load_index() if index is None else index
    matches = find_matches(cleaned, idx) if idx else []
    final = apply_matches(cleaned, matches) if matches else cleaned
    meta = {
        "lang": lang,
        "removed": removed,
        "swaps": [{"span": m["span"], "to": m["canonical"], "method": m["method"]}
                  for m in matches],
    }
    return final, meta
