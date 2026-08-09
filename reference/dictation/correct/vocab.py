"""
vocab.py — derive the vocabulary FROM YOUR CORPUS, so it cannot go stale the way
a hand-maintained list does.

Produces two artifacts, both written to DICTATION_HOME:

  vocab_prompt.txt   a flat comma-separated string, fed to whisper as --prompt
                     to bias the acoustic model toward your proper nouns.
  vocab_index.json   a structured index used by the correction matcher.

Index entry shape:
    {id, canonical, norm, meta, acronym, freq}
      canonical  the spelling as it appears in the corpus — what gets swapped IN,
                 so casing is preserved (PagerDuty, not Pagerduty)
      norm       lowercased, stripped to [a-z0-9]; the match surface
      meta       metaphone of norm; the phonetic key
      freq       corpus frequency; picks between surface forms and filters noise

Extraction heuristics: all-caps acronyms, CamelCase, hyphenated forms, and
capitalised tokens appearing MID-sentence (a much stronger proper-noun signal
than sentence-initial capitalisation). Code fences are stripped first — variable
names make terrible dictation vocabulary.

Known gap: lowercase domain terms (kubelet, containerd) are invisible to
capitalisation heuristics. Closing it needs a frequency + not-in-dictionary pass.

Run:  python3 -m dictation build-vocab
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import jellyfish as jf

from .. import config

STOPWORDS = {
    # sentence starters, modals, pronouns
    "The", "A", "An", "I", "We", "He", "She", "It", "They", "You", "My", "His",
    "Her", "Their", "Our", "Your", "This", "That", "These", "Those", "And",
    "Or", "But", "So", "Also", "Then", "If", "When", "While", "After", "Before",
    "Now", "Today", "Yesterday", "Tomorrow", "Will", "Would", "Should", "Could",
    "Can", "Cannot", "Do", "Does", "Did", "Have", "Has", "Had", "Be", "Been",
    "Being", "Am", "Is", "Are", "Was", "Were", "Not", "No", "Yes", "Maybe",
    "Some", "Any", "All", "Most", "Each", "Every", "Other", "Another", "More",
    "Less", "Few", "Many", "Much", "Very", "Just", "Only", "Use", "Used",
    "Using", "Make", "Made", "Get", "Got", "Go", "Going", "See", "Saw", "Take",
    "Took", "Give", "Gave", "Find", "Found", "Next", "Last", "First", "Second",
    "Third", "Final", "Here", "There", "Where", "Why", "How", "What", "Which",
    "Who",
    # days and months — whisper handles these fine unaided
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    # markdown / document furniture
    "Notes", "Note", "Status", "Source", "Sources", "Result", "Results", "Open",
    "Closed", "Done", "TODO", "TBD", "Pending", "Active", "Update", "Updates",
    "Updated", "New", "Old", "Section", "Sections", "Part", "Parts", "Item",
    "Items", "Overview", "Summary", "Example", "Warning", "Caution",
}

# Alphanumerics, optionally hyphenated, starting with a letter. Hyphens are
# in-word (Kube-Bench, Aqua-Security); en/em dashes are not.
WORD_RE = re.compile(r"\b[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9'’]*(?:-[A-Za-zÀ-ÿ0-9'’]+)*\b")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def is_candidate(token: str, pos: int) -> bool:
    """pos == 0 means sentence-initial, which is a weak proper-noun signal."""
    if token in STOPWORDS or len(token) < 2:
        return False
    if token.isupper() and any(c.isalpha() for c in token):
        return True                                    # SLO, CRD, SRE
    if any(c.isupper() for c in token[1:]) and any(c.islower() for c in token):
        return True                                    # CamelCase / PascalCase
    if token[0].isupper() and pos > 0:
        return True                                    # capitalised mid-sentence
    if token[0].isupper() and pos == 0 and len(token) > 4:
        return True                                    # unusual sentence starter
    return False


def _corpus_files() -> list[Path]:
    files: list[Path] = []
    for root in config.CORPUS_ROOTS:
        if not root.exists():
            continue
        for pat in config.CORPUS_GLOBS:
            files.extend(p for p in root.glob(pat) if p.is_file())
    return files


def count_terms() -> Counter:
    counts: Counter = Counter()
    for path in _corpus_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        text = re.sub(r"```[\s\S]*?```", "", text)     # strip code fences
        for sentence in re.split(r"(?<=[.!?\n])\s+", text):
            for i, tok in enumerate(WORD_RE.findall(sentence)):
                if is_candidate(tok, i):
                    counts[tok] += 1
    return counts


def build_index(counts: Counter) -> list[dict]:
    """Dedupe case-insensitively; the most frequent surface form is canonical."""
    by_norm: dict[str, Counter] = {}
    for term, c in counts.items():
        by_norm.setdefault(norm(term), Counter())[term] += c
    entries = []
    for i, (n, surfaces) in enumerate(sorted(by_norm.items())):
        if len(n) < 2:
            continue
        canonical = surfaces.most_common(1)[0][0]
        entries.append({
            "id": i,
            "canonical": canonical,
            "norm": n,
            "meta": jf.metaphone(n),
            "acronym": canonical.isupper(),
            "freq": sum(surfaces.values()),
        })
    return entries


def build_prompt(counts: Counter, limit: int) -> str:
    """The whisper --prompt bias string.

    Whisper biases best when the prompt reads like ordinary prose rather than a
    wordlist dump, and the prompt eats context window — so cap it (~120 terms /
    ~200 tokens is comfortable).
    """
    top = [t for t, _ in counts.most_common(limit)]
    return "Discussion topics include: " + ", ".join(top) + "."


def load_index() -> list[dict]:
    if config.VOCAB_INDEX_FILE.exists():
        return json.loads(config.VOCAB_INDEX_FILE.read_text(encoding="utf-8"))
    return []


def rebuild() -> tuple[int, int]:
    """Regenerate both artifacts. Returns (index_entries, prompt_terms)."""
    config.ensure_home()
    counts = count_terms()
    if not counts:
        return 0, 0
    index = build_index(counts)
    prompt = build_prompt(counts, config.VOCAB_PROMPT_TERMS)
    config.VOCAB_INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    config.VOCAB_PROMPT_FILE.write_text(prompt + "\n", encoding="utf-8")
    return len(index), min(len(counts), config.VOCAB_PROMPT_TERMS)
