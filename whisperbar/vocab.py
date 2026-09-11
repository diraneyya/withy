"""
vocab.py — the vocabulary file.

One plain text file, at ~/.config/whisperbar/vocabulary.txt. Terms are
separated by whitespace or newlines; `#` starts a comment. That is the whole
format:

    # project names
    Kubernetes  PagerDuty  Grafana
    OrwaTech
    Kleinanzeigen

It is deliberately NOT derived from a corpus. An auto-derived index of a few
thousand terms was measured on 360 real dictations and made the text worse 63%
of the time it fired — at that size, almost any spoken word collides with
something. A hand-written list of tens of terms has a collision surface small
enough to be safe, and the user can see and fix every entry.

The file feeds three places:
  1. whisper's `--prompt` bias, so the terms are more likely to be heard right
  2. the deterministic spacing/acronym rules in correct.py
  3. the post-processing model's context, as "these are this person's words"
"""

from __future__ import annotations

import re

from . import config

SAMPLE = """\
# Whisperbar vocabulary
#
# Words the speech model would otherwise get wrong: project names, product
# names, acronyms, colleagues' names, jargon. Separate them with spaces or
# newlines. Lines starting with # are ignored.
#
# Keep this list SHORT and specific. Every entry is a chance to correct a
# word — and a chance to corrupt one. Do not add ordinary English words.

# examples — replace these with your own
Kubernetes PagerDuty Grafana Terraform
"""


def ensure_file() -> None:
    """Create the vocabulary file with an explanatory sample on first run."""
    config.ensure_dirs()
    if not config.VOCAB_FILE.exists():
        config.VOCAB_FILE.write_text(SAMPLE, encoding="utf-8")


def load() -> list[str]:
    """Terms in file order, de-duplicated, comments stripped."""
    if not config.VOCAB_FILE.exists():
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for line in config.VOCAB_FILE.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        for tok in line.split():
            if tok and tok.lower() not in seen:
                seen.add(tok.lower())
                terms.append(tok)
    return terms


def norm(s: str) -> str:
    """Match surface: lowercase, letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def by_norm(terms: list[str]) -> dict[str, str]:
    """{normalised form: canonical spelling}. First spelling wins."""
    d: dict[str, str] = {}
    for t in terms:
        n = norm(t)
        if n and n not in d:
            d[n] = t
    return d


def whisper_prompt(terms: list[str], limit: int = 200) -> str:
    """The `--prompt` bias string. Whisper treats this as preceding context, so
    a comma-separated list of names reads naturally enough to bias decoding."""
    return ", ".join(terms[:limit])
