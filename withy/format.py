"""
format.py — the post-processing pass: punctuation, structure, self-corrections.

This is the stage that closes the gap with commercial cloud dictation. It adds
what speech does not contain: sentence punctuation, paragraph breaks, quotation
marks around reported speech, list structure, and the application of spoken
self-corrections ("no, scratch that, make it Tuesday").

None of that is a deterministic problem, so it uses a local model. But a small
instruct model given an open brief WILL rewrite meaning — that failure is on
record, from an earlier attempt to use one for word-level correction. The
defence is not a better prompt. It is `gate()`.

THE GATE
    Every word in the output must be a word that was spoken ANYWHERE in this
    dictation, a term from the user's vocabulary file, or a list marker.
    Punctuation, casing and line breaks are unconstrained; content is not. If
    the model invents a word, the whole output is discarded and the unformatted
    transcript is typed instead.

    Note the exact guarantee, because it is weaker than "the words are
    unchanged": the check is against a SET, so the model may repeat or move a
    word it has already seen. That deliberately permits small grammatical
    repairs ("there's always mucous membrane" -> "there's always A mucous
    membrane", where "a" occurs earlier in the same dictation) at the cost of
    not detecting a reordering. It cannot introduce a subject, a name, a
    number or a claim that was never spoken, which is the failure that
    matters.

So the worst case is not corruption — it is that formatting silently doesn't
happen. That asymmetry is the entire design.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import urllib.error
import urllib.request

from . import config
from .log import log
from .vocab import norm

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

def _api_key() -> str | None:
    """The hosted-backend key.

    Read from a file rather than settings.json, because settings.json is edited
    by the menu and printed by `withy settings` — a secret does not belong in
    something routinely dumped to a terminal. The file should be mode 600.
    Falls back to the environment for people who already export it.
    """
    f = config.CONFIG_DIR / "openai-key"
    if f.exists():
        k = f.read_text(encoding="utf-8").strip()
        if k:
            return k
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("WITHY_OPENAI_KEY")


def _openai(model: str, prompt: str, timeout: int) -> str | None:
    """Hosted polishing. NOTE: this sends the transcript off the machine — the
    one part of Withy that is not local. It is opt-in and off by default, and
    the menu says so."""
    key = _api_key()
    if not key:
        log("format: no API key — put one in ~/.config/withy/openai-key")
        return None
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return (data["choices"][0]["message"]["content"] or "").strip()
    except urllib.error.HTTPError as e:
        log(f"format: openai HTTP {e.code}: {e.read()[:200]!r}")
    except (urllib.error.URLError, TimeoutError, KeyError,
            IndexError, json.JSONDecodeError, OSError) as e:
        log(f"format: openai call failed: {type(e).__name__}: {e}")
    return None


def _call_model(prompt: str) -> str | None:
    """Dispatch to whichever polishing backend is configured."""
    s = config.settings()
    timeout = int(s["llm_timeout"])
    if str(s.get("polish_backend", "local")) == "openai":
        return _openai(str(s.get("openai_model", "gpt-4.1-mini")), prompt, timeout)
    return _ollama(str(s["llm_model"]), prompt, timeout)


# Chunk length is the single most important number in this file.
#
# Measured on a real dictation containing a spoken self-correction ("...and
# prose CONTENT context, so graph-shaped context and prose-SHAPED context"):
#
#   passage alone, 30 words   -> restatement collapsed, stutter removed
#   same passage in 117 words -> nothing removed at all
#
# The model does not get worse at the task; it gets worse at holding the
# instruction over distance. This is the same positional degradation that
# shows up in diacritization and speech synthesis past ~30 words, and the fix
# is the same: feed it sentence-sized pieces.
CHUNK_WORDS = 40

# Below this ratio of surviving content words, assume the model truncated
# rather than applied a self-correction. Enforced strictly only on longer
# input: retracting half of a twelve-word sentence is normal speech ("Monday,
# no scratch that, Tuesday"), whereas losing half of a 200-word dictation is
# always the model giving up early.
MIN_KEEP_RATIO_LONG = 0.5
MIN_KEEP_RATIO_SHORT = 0.25
RATIO_STRICT_ABOVE = 40

PROMPT = """\
You format dictated speech into written text.

Return the SAME WORDS the speaker said, with formatting applied. You may:
- add punctuation, capitalisation, paragraph breaks
- put quotation marks around speech the speaker is quoting or acting out.
  Quote ONLY the words being attributed to someone. Never wrap the whole
  text in quotation marks
- turn a spoken enumeration into a numbered or bulleted list
- delete filler words and false starts
- apply spoken self-corrections: if the speaker retracts something ("no,
  scratch that", "sorry, I mean"), delete the retracted text and keep the
  correction, including the words of the retraction itself

You must NEVER:
- add a word the speaker did not say
- replace a word with a different word
- summarise, shorten, expand or rephrase anything
- comment on the text or explain what you did
- use markdown, bold, italics or asterisks of any kind

Output the formatted text and nothing else.{vocab}

Transcript:
{text}"""

VOCAB_HINT = """

These are the speaker's own terms. If a word looks like a garbled attempt at \
one of them, use the correct spelling; otherwise leave every word alone:
{terms}"""


def _ollama(model: str, prompt: str, timeout: int) -> str | None:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        # Deterministic: this is a rewriting task with one right answer shape.
        "options": {"temperature": 0, "top_p": 1, "repeat_penalty": 1.0},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "").strip()
    except urllib.error.URLError as e:
        log(f"format: ollama unreachable ({e}) — is `ollama serve` running?")
    except (TimeoutError, json.JSONDecodeError, OSError) as e:
        log(f"format: ollama call failed: {type(e).__name__}: {e}")
    return None


_EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*?|__)(?=\S)(.+?)(?<=\S)\1(?!\w)", re.S)


def _strip_markdown(text: str) -> str:
    """Remove markdown emphasis the model adds around words it changed.

    Observed live: a corrected proper noun came back as `**Homebrew**`. The gate
    cannot see it — normalisation strips punctuation — so it would have been
    typed literally, asterisks and all. Dictated speech effectively never
    contains paired asterisks, so removing them is safe.
    """
    prev = None
    while prev != text:
        prev = text
        text = _EMPHASIS_RE.sub(r"\2", text)
    return text


def _unwrap_quotes(text: str) -> str:
    """Strip a pair of quotes the model wrapped around its whole answer.

    Small instruct models habitually return their output as a quoted string.
    That is indistinguishable, in the prompt, from being asked to quote speech —
    so it is removed here instead: if the text opens and closes with a double
    quote and contains no OTHER double quote, the pair is a wrapper, not
    reported speech (which would put quotes somewhere in the middle too).
    """
    t = text.strip()
    if len(t) > 1 and t[0] in '"\u201c' and t[-1] in '"\u201d':
        if sum(t.count(c) for c in '"\u201c\u201d') == 2:
            return t[1:-1].strip()
    return text


def _content_tokens(text: str) -> list[str]:
    return [t for t in (norm(w) for w in text.split()) if t]


def gate(raw: str, formatted: str, terms: list[str]) -> tuple[bool, str]:
    """Is `formatted` a faithful reformatting of `raw`? Returns (ok, reason)."""
    if not formatted.strip():
        return False, "empty output"

    allowed = set(_content_tokens(raw))
    allowed |= {norm(t) for t in terms}
    # Splitting a vocabulary term the model spelled as separate words, plus the
    # digits and markers a list introduces.
    allowed |= {str(i) for i in range(1000)}

    out = _content_tokens(formatted)
    if not out:
        return False, "no content in output"

    def _ok(tok: str) -> bool:
        if tok in allowed or tok.isdigit():
            return True
        # The model may hyphenate or join two spoken words ("learning-related",
        # "planner.So"). Both normalise to a single token that was never spoken
        # as one, but neither invents content — so accept a token that splits
        # cleanly into allowed pieces.
        for i in range(2, len(tok) - 1):
            if tok[:i] in allowed and tok[i:] in allowed:
                return True
        return False

    invented = [t for t in out if not _ok(t)]
    if invented:
        return False, f"invented {len(invented)} word(s): {invented[:5]}"

    n_in = len(_content_tokens(raw))
    kept = len(out) / max(1, n_in)
    floor = MIN_KEEP_RATIO_LONG if n_in >= RATIO_STRICT_ABOVE else MIN_KEEP_RATIO_SHORT
    if kept < floor:
        return False, f"dropped {(1 - kept):.0%} of content"

    return True, "ok"


_TOKEN_RE = re.compile(r"(\S+)(\s*)")


def _split_keep_space(text: str) -> list[tuple[str, str]]:
    """[(word, trailing whitespace)] — the whitespace carries paragraph breaks."""
    return [(m.group(1), m.group(2)) for m in _TOKEN_RE.finditer(text)]


def reconcile(raw: str, formatted: str, terms: list[str]) -> tuple[str, int]:
    """Keep the model's FORMATTING while refusing its word substitutions.

    The gate below is all-or-nothing, and that turned out to be far too blunt in
    practice: the model corrected one word ("y'all" -> "your") in a paragraph,
    and the whole paragraph lost its capitalisation and its quotation marks.
    The formatting was never the problem — one word was.

    So instead of accepting or rejecting the output, align it against what was
    actually said and take, token by token:

      equal    -> the model's version, which carries the punctuation and casing
      deleted  -> nothing; removing filler and retracted text is the point
      inserted -> only vocabulary terms and list markers; never a new word
      replaced -> the model's version ONLY if every token is a vocabulary term
                  (that is what licenses "Homebro" -> "Homebrew"); otherwise the
                  spoken words come back verbatim

    The guarantee is therefore stronger than before, not weaker: no word can be
    substituted for one that was never said — and the formatting still lands.
    Returns (text, number of reverted substitutions).
    """
    rtoks = _split_keep_space(raw)
    ftoks = _split_keep_space(formatted)
    vocab_norms = {norm(t) for t in terms}
    rn = [norm(w) for w, _ in rtoks]
    fn = [norm(w) for w, _ in ftoks]

    out: list[tuple[str, str]] = []
    reverted = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=rn, b=fn, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(ftoks[j1:j2])
        elif tag == "delete":
            continue
        elif tag == "insert":
            for w, ws in ftoks[j1:j2]:
                n = norm(w)
                if n in vocab_norms or n.isdigit() or not n:
                    out.append((w, ws))
                else:
                    reverted += 1
        else:  # replace
            block = ftoks[j1:j2]
            if block and all(norm(w) in vocab_norms for w, _ in block):
                out.extend(block)
            else:
                out.extend(rtoks[i1:i2])
                reverted += 1

    text = "".join(w + (ws or " ") for w, ws in out).strip()
    return text, reverted


_ENDS_SENTENCE = re.compile(r"""[.!?]["')\]]*\s*$""")


def _match_leading_case(raw_chunk: str, formatted: str) -> str:
    """Undo the capital the model puts on a chunk that is not a new sentence.

    Each chunk is handed to the model on its own, so it capitalises the first
    word every time — which is correct for a sentence and wrong for the second
    half of one. Whether it really starts a sentence is decided by the previous
    chunk's punctuation, and the evidence for the right casing is the spoken
    word itself: if Whisper wrote it lower-case, it is not a proper noun.
    """
    rw = raw_chunk.split()
    fw = formatted.split()
    if not rw or not fw:
        return formatted
    first_raw = rw[0].lstrip("\"'([")
    if first_raw[:1].islower():
        for i, ch in enumerate(formatted):
            if ch.isalpha():
                return formatted[:i] + ch.lower() + formatted[i + 1:]
    return formatted


_SENTENCE_START = re.compile(r"""([.!?]["')\]]*[ \t]+|\n+)([a-z])""")


def capitalise_sentences(text: str) -> str:
    """Capitalise after every sentence ending.

    Speech contains no capital letters at all, so this cannot be left to the
    model: it capitalises reliably in some places and not others, and the misses
    are glaring ("...prose-shaped context. and for that..."). Requiring
    whitespace after the punctuation keeps decimals ("3.5 metres") intact.
    """
    return _SENTENCE_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def capitalise_first(text: str) -> str:
    """Upper-case the first letter. Speech has no capital letters, so this must
    never depend on the model remembering to do it."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1:]
        if not ch.isspace() and ch not in "\"'([":
            break
    return text


# Real English prose runs about 0.05-0.15 commas per word. A small model that
# loses the thread emits one comma per word — observed live, a whole paragraph
# returned as "ones, maybe, some, other, issue, will, happen, and, by, the, ...".
# Word-level reconciliation accepts that happily, because every word IS one that
# was spoken; it is the punctuation that has gone mad. So the formatting needs a
# sanity check of its own, separate from the content check.
MAX_COMMA_RATE = 0.35
MIN_WORDS_PER_LINE = 2.0


def formatting_sane(raw: str, formatted: str) -> tuple[bool, str]:
    """Is this plausibly prose, rather than a degenerate list of tokens?"""
    words = formatted.split()
    if not words:
        return False, "no words"

    rate = formatted.count(",") / len(words)
    if rate > MAX_COMMA_RATE and formatted.count(",") > raw.count(",") + 3:
        return False, f"{rate:.2f} commas per word"

    lines = [l for l in formatted.splitlines() if l.strip()]
    if len(lines) > 3 and len(words) / len(lines) < MIN_WORDS_PER_LINE:
        return False, f"{len(words)/len(lines):.1f} words per line"

    return True, "ok"


def _split_long(sentence: str, size: int) -> list[str]:
    """Break a sentence that is longer than `size` words.

    Dictated speech is full of sentences far longer than any written one — a
    single unpunctuated run of 60+ words is normal when someone is thinking out
    loud. Splitting only on sentence boundaries therefore cannot get below the
    length at which the model stops following instructions. Prefer commas and
    other natural pauses; hard-split on word count only as a last resort.
    """
    words = sentence.split()
    if len(words) <= size:
        return [sentence]
    parts, cur = [], []
    for piece in re.split(r"(?<=[,;:])\s+", sentence):
        pw = len(piece.split())
        if cur and sum(len(c.split()) for c in cur) + pw > size:
            parts.append(" ".join(cur))
            cur = []
        cur.append(piece)
    if cur:
        parts.append(" ".join(cur))
    out = []
    for part in parts:
        w = part.split()
        if len(w) <= size * 1.5:
            out.append(part)
        else:            # no punctuation to lean on at all
            for i in range(0, len(w), size):
                out.append(" ".join(w[i:i + size]))
    return out


def _chunks(text: str, size: int = CHUNK_WORDS) -> list[str]:
    """Sentence-sized pieces, never much longer than `size` words."""
    pieces: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        pieces.extend(_split_long(sent, size))
    out, cur, n = [], [], 0
    for piece in pieces:
        w = len(piece.split())
        if cur and n + w > size:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(piece)
        n += w
    if cur:
        out.append(" ".join(cur))
    return [c for c in out if c.strip()] or [text]


def format_text(raw: str, terms: list[str], lang: str = "en") -> tuple[str, dict]:
    """Format `raw`. On any failure returns `raw` unchanged — never raises."""
    s = config.settings()
    if not s["postprocess"] or not raw.strip():
        return raw, {"applied": False, "reason": "disabled"}

    model, timeout = s["llm_model"], int(s["llm_timeout"])
    # Non-English speech is passed through untouched: the prompt, the model and
    # the gate's dictionary sense are all English, and a measured Arabic sample
    # produced an empty response that the gate correctly threw away — a wasted
    # call on every non-English dictation.
    if lang and lang != "en":
        return raw, {"applied": False, "reason": f"language {lang}"}
    vocab = VOCAB_HINT.format(terms=", ".join(terms[:200])) if terms else ""

    # The 40-word ceiling is a property of a 3B local model, not of the task.
    # A hosted model holds the instruction far further, and fewer boundaries
    # means fewer split quotes and better paragraphing.
    size = int(s.get("chunk_words") or
               (200 if str(s.get("polish_backend", "local")) == "openai"
                else CHUNK_WORDS))

    pieces, reasons = [], []
    for chunk in _chunks(raw, size):
        resp = _call_model(PROMPT.format(vocab=vocab, text=chunk))
        if resp is None:
            return raw, {"applied": False, "reason": "model unavailable"}
        # Small models like to wrap output in a code fence or preamble.
        resp = re.sub(r"^```[a-z]*\n|\n```$", "", resp.strip())
        resp = _unwrap_quotes(_strip_markdown(resp))
        # Catastrophic failures (empty output, the model giving up half way)
        # still discard the chunk; word-level disagreements are reconciled.
        ok, why = gate(chunk, resp, terms)
        if not ok and ("empty" in why or "dropped" in why or "no content" in why):
            log(f"format: DISCARDED chunk ({why}) — keeping raw")
            reasons.append(why)
            pieces.append(chunk)
            continue
        merged, reverted = reconcile(chunk, resp, terms)
        sane, why_insane = formatting_sane(chunk, merged)
        if not sane:
            log(f"format: DISCARDED chunk (degenerate formatting: {why_insane})")
            reasons.append(why_insane)
            pieces.append(chunk)
            continue
        # A chunk boundary is an artefact of how the text was fed to the
        # model, not a structural break in what was said — so it must not
        # become a paragraph break or a capital letter mid-sentence.
        # Casing at a chunk join is decided by the PREVIOUS chunk's
        # punctuation, in both directions: after a full stop the next piece
        # starts a sentence and must be capitalised; mid-sentence it must not
        # be, however the model chose to render it in isolation.
        if pieces:
            if _ENDS_SENTENCE.search(pieces[-1]):
                merged = capitalise_first(merged)
            else:
                merged = _match_leading_case(chunk, merged)
        if reverted:
            log(f"format: reverted {reverted} substitution(s), kept formatting")
        pieces.append(merged)

    # Joined with a space, not a blank line: paragraph breaks are the model's
    # to make INSIDE a chunk, where it can see the meaning.
    final = capitalise_sentences(capitalise_first(" ".join(pieces).strip()))
    applied = not reasons or len(reasons) < len(pieces)
    return final, {"applied": applied, "model": model,
                   "chunks": len(pieces), "rejected": reasons}
