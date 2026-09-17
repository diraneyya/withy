"""
vocab.py — the vocabulary, from two places and in two kinds.

TWO PLACES.

  ~/.config/withy/vocabulary.txt   yours
  withy/vocabulary.d/*.txt         shipped with the code

The second exists for downstream forks. An organisation has internal tools and
product names that speech-to-text will never get right, and those belong with
the code rather than in every employee's config file. A DIRECTORY rather than
one shared file, deliberately: a fork that edited a single `vocabulary.txt`
would collide with upstream on that file at every pull, forever. Separate files
never conflict, so a fork adds `acme.txt` and merges from origin cleanly.

Unlike the polishing instructions, this needs no ancestor, no merge and no
dialog — a vocabulary is a config file in the strict sense, one independent
item per line. Two sources combine by union and cannot contradict each other.
Yours wins on a spelling disagreement, because you are the one who has to read
the output.

TWO KINDS.

A term needs the model only when the words that produce it could also be
something else. "Forge Joe" is nobody's sentence, so joining it to "Forgejo"
is safe with no context at all. "C file" is a real thing a programmer says, so
deciding whether it meant "Seafile" requires the sentence around it.

    [deterministic]   fixed by exact match, before the model runs
    [context]         given to the model, which judges by meaning  (the default)

Everything is `context` unless a file says otherwise, so a careless list cannot
silently corrupt speech: the author opts IN to deterministic handling.

This also solves the prompt's term budget. Only context terms have to be listed
for the model, so a company list of hundreds costs almost nothing — and when
there is room left, deterministic terms are listed too, because exact matching
only catches the spacing garble ("forge joe") and not a near miss ("forge job").

⚠️ Do not let two buckets become a reason for a long list. An auto-derived index
of a few thousand terms was measured on 360 real dictations and made the text
WORSE 63% of the time it fired: at that size almost any spoken word collides
with something. Tens of terms is a safe collision surface. Thousands is not,
in either bucket.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import config

# Shipped alongside the code, so a fork's terms travel with its checkout.
STOCK_DIR = Path(__file__).resolve().parent / "vocabulary.d"

SAMPLE = """\
# Withy vocabulary
#
# Words the speech model would otherwise get wrong: project names, product
# names, acronyms, colleagues' names, jargon. Separate them with spaces or
# newlines. Lines starting with # are ignored.
#
# Keep this list SHORT and specific. Every entry is a chance to correct a
# word — and a chance to corrupt one. Do not add ordinary English words.
#
# Terms are given to the polishing model, which decides from the sentence
# whether a word was really a garbled attempt at one of them. If a term could
# never be confused with ordinary English — a made-up product name — you can
# put it under a [deterministic] heading instead and it will be corrected by
# exact match, without needing the model at all:
#
#     [deterministic]
#     Kubernetes  Grafana  Forgejo
#
# Examples, commented out. Uncomment or replace with your own:
#
#   Kubernetes PagerDuty Grafana Terraform
#
# Nothing below this line is active until you remove the leading #.
"""

_SECTION_RE = re.compile(r"^\[\s*(deterministic|context)\s*\]$", re.I)


@dataclass(frozen=True)
class Term:
    text: str
    deterministic: bool
    source: str          # a label for `withy vocab`, not a path to open


def ensure_file() -> None:
    """Create the user's vocabulary file with an explanatory sample."""
    config.ensure_dirs()
    if not config.VOCAB_FILE.exists():
        config.VOCAB_FILE.write_text(SAMPLE, encoding="utf-8")


def parse(text: str, source: str) -> list[Term]:
    """Terms in file order. `[deterministic]` / `[context]` switch the bucket."""
    out: list[Term] = []
    det = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = _SECTION_RE.match(line)
        if m:
            det = m.group(1).lower() == "deterministic"
            continue
        for tok in line.split():
            out.append(Term(tok, det, source))
    return out


def load_terms() -> list[Term]:
    """Everything, de-duplicated. The user's spelling wins a disagreement."""
    found: list[Term] = []
    if config.VOCAB_FILE.exists():
        try:
            found += parse(config.VOCAB_FILE.read_text(encoding="utf-8"), "yours")
        except OSError:
            pass
    if STOCK_DIR.is_dir():
        for f in sorted(STOCK_DIR.glob("*.txt")):
            try:
                found += parse(f.read_text(encoding="utf-8"), f.stem)
            except OSError:
                continue
    out: list[Term] = []
    seen: set[str] = set()
    for t in found:
        n = norm(t.text)
        if n and n not in seen:
            seen.add(n)
            out.append(t)
    return out


def load() -> list[str]:
    """Every term, as plain strings. The gate's allowlist wants all of them."""
    return [t.text for t in load_terms()]


def split() -> tuple[list[str], list[str]]:
    """(deterministic, context) — which stage may act on each term."""
    terms = load_terms()
    return ([t.text for t in terms if t.deterministic],
            [t.text for t in terms if not t.deterministic])


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


def prompt_terms(limit: int = 200) -> list[str]:
    """What to list for the model, in priority order.

    Context terms first because they are the ones that CANNOT be handled any
    other way. Deterministic terms fill whatever budget is left: exact matching
    already catches their spacing garble, but the model can also catch a near
    miss that exact matching cannot, so listing them is worth doing when there
    is room and worth dropping first when there is not.
    """
    det, ctx = split()
    return (ctx + det)[:limit]


def whisper_prompt(terms: list[str], limit: int = 200) -> str:
    """The `--prompt` bias string. Whisper treats this as preceding context, so
    a comma-separated list of names reads naturally enough to bias decoding."""
    return ", ".join(terms[:limit])
