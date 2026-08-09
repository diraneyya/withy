# 03 — The correction engine

Whisper is good. It is not good at *your* proper nouns, and it faithfully
transcribes the "um"s that nobody wants typed. This stage fixes both, using **no
model at all**.

Reference: `reference/dictation/correct/`.

That "no model" is the finding, not an accident. It was reached by trying the
obvious thing first and measuring the damage.

> **A note on the examples.** The failures below were observed in a system whose
> corpus was a personal notes repo. The examples here have been re-derived
> against a generic infrastructure vocabulary (Grafana, Kubernetes, PagerDuty,
> Node, DAGs …) so they are meaningful in an engineering context. Every phonetic
> collision shown is real and computable — `jellyfish.metaphone("need")` and
> `jellyfish.metaphone("node")` are both `NT`. The *shape* of each failure is what
> transferred; the specific words are recomputed, not invented.

---

## What was tried, and what it cost

Four experiments, run over seven realistic messy transcripts with known ground
truth. Environment: Ollama with `qwen2.5:0.5b` and `qwen2.5:1.5b`, M2 Pro / 16 GB.
Latency was never the problem — 0.08–0.41 s warm, ~1.2 s cold. **Discipline was.**

### 1. Open-ended "correct this transcript"

- **0.5b: disqualified.** On the clean control transcript it hallucinated an
  *answer* to the question instead of returning it. Silently dropped words. Made
  some garbles worse.
- **1.5b: better, still unsafe.** Clean on the control, and its own world knowledge
  fixed a well-known compound term for free. But it **rewrote meaning in 2 of 7**:
  one clause became a different claim entirely, and a sentence containing a
  company name collapsed into nonsense with the name corrupted.

> The risk that matters with a small local model is not latency and not
> vocabulary. It is that it rewrites things you did not ask it to rewrite, and
> you cannot see that it did.

### 2. Constrained edit operations (deletion spans only)

The model returns spans to delete; code applies them; a guardrail rejects any
result that is not a word-level **subsequence** of the input (deletions only, no
additions). Fail-safe returns the input untouched.

- ✅ Hallucination eliminated. The guardrail held in every case.
- ❌ Traded for **over-deletion**. It deleted a company name outright, a vendor
  name, half of a product model number, and the word "and" from a list. Meaning
  destroyed in 5 of 7.

**The meta-lesson, which generalises well beyond dictation:**

> A subsequence guardrail bounds a model **from above** (it cannot add) but not
> **from below** (it can over-delete). Forbidding invention is necessary and not
> sufficient. You also need a *positive* rule: a whitelist of what may be removed,
> or a closed set of what may be substituted.

### 3. Deterministic filler and stutter removal

Pure code. A fixed filler set, immediate duplicate collapse, a few multi-word
hedges.

- ✅ **Perfect on all 7.** Every `um`/`uh` and the `the the` stutter removed;
  nothing else touched. Every proper noun, model number, and article survived. The
  control case came out byte-identical.

Free, instant, and safe *by construction* — it can only remove tokens on a fixed
list, so it can never touch a content word.

### 4. Corpus-grounded proper-noun correction

The first attempt maximised recall: phonetically compare every 1–3 token span
against a 3,475-entry index extracted from the corpus.

**It exploded.** 65 swaps, 49 of them ambiguous, and the clean control transcript
destroyed. In a generic infrastructure vocabulary the same collisions are trivial
to reproduce:

| ordinary word | metaphone | corpus term it collides with |
|---|---|---|
| `need`, `note`, `not` | `NT` | **Node**, **Netty** |
| `docs`, `tags` | `TKS` | **DAGs** |
| `apps` | `APS` | **APIs** |
| `reads` | `RTS` | **Redis** |
| `stacks` | `STKS` | **SDKs** |

The cause is worth internalising, because it is not a tuning problem:

> On an index of a few thousand terms, almost any short span shares an exact
> phonetic key with *some* entry. String similarity **cannot** separate the good
> match from the bad one — `need↔Node` and `graphana↔Grafana` are both exact
> metaphone matches with comparable edit distance. The only discriminator is that
> "need" is a real English word and "graphana" is not.

Rewritten precision-first: **8 swaps, 0 ambiguous, all correct, control untouched.**

---

## The three rules that shipped

Each is narrow and each is gated. Reference: `correct/match.py`.

| Rule | Gate | Recovers |
|---|---|---|
| **concat-exact** | join 2–3 adjacent tokens; swap only if the joined, normalised form **exactly equals** a corpus term | `pager duty → PagerDuty`, `data dog → Datadog`, `terra form → Terraform` |
| **spoken-letter** | a run of letter-name tokens (`ess ell oh`) → acronym, accepted only if that acronym is exactly a corpus term | `ess ell oh → SLO`, `ay pee eye → API`, `see are dee → CRD` |
| **oov-metaphone** | a **single** token that is *not* in the system dictionary, *not* already a corpus term, with an **exact** metaphone match to one | `graphana → Grafana`, `kubernetis → Kubernetes`, `promethius → Prometheus` |

Conflicts are resolved greedily: longer spans first, exact-match rules before the
phonetic one, no overlapping replacements.

### What it deliberately does not fix

Real-word garbles where every token is a valid English word: `easy two → EC2`,
`cube control → kubectl`, `page duty → PagerDuty` (note that this one *fails* the
concat gate — "pageduty" ≠ "pagerduty" — while `pager duty` passes it). Also
number words and acronym expansion.

No deterministic gate can flag these — nothing about "cube control" is anomalous.
That is a *choice*, and it is the right one:

> A false correction corrupts silently and may survive review. A miss is visible
> and the user fixes it in one keystroke. For a corrector, precision ≫ recall.

If you want those cases later, the shape is: a candidate generator proposes a
**closed set** of options for a suspicious span, a model **selects an ID or
"none"** using sentence context, and code validates and swaps. The model never
spells anything — it only picks from a list. That keeps the positive-rule property
from experiment 2. Not built here.

---

## The vocabulary index

`correct/vocab.py` walks your corpus and extracts proper-noun candidates, so the
vocabulary **cannot go stale** the way a hand-maintained list does.

Each entry:

```json
{"id": 412, "canonical": "Kubernetes", "norm": "kubernetes",
 "meta": "KBRNTS", "acronym": false, "freq": 87}
```

- `canonical` — the spelling as it appears in your corpus; this is what gets
  swapped in, so casing is preserved correctly (`PagerDuty`, not `Pagerduty`).
- `norm` — lowercased, stripped of everything but `[a-z0-9]`; the match surface.
- `meta` — [metaphone](https://en.wikipedia.org/wiki/Metaphone) of `norm`, the
  phonetic key (via the `jellyfish` package).
- `freq` — corpus frequency; used to pick between same-normalisation surface forms
  and to filter out one-off noise (`MIN_FREQ = 4`).

Extraction heuristics: all-caps acronyms of 2+ letters, CamelCase, hyphenated
forms, and capitalised tokens appearing **mid-sentence** (a much stronger
proper-noun signal than sentence-initial capitalisation). Code fences are stripped
first — variable names make terrible dictation vocabulary. A stoplist removes
common sentence starters, weekdays, and months.

**Known gap:** lowercase domain terms (`kubelet`, `containerd`, `systemd`) are
invisible to capitalisation heuristics. Closing it means a frequency-plus-not-in-
dictionary pass. Not built.

### Corpus choices for a company

In rough order of value per unit of effort:

1. **Service and repo names** — from your service catalogue or a `git ls-remote`
   sweep. Highest hit rate; these are what people actually say out loud.
2. **Internal wiki / runbook titles.**
3. **Team, tool, and product names** — the acronym soup every company has.
4. **Employee display names** — enormously useful for dictating messages, and the
   most privacy-sensitive input here. Keep the index local to the device, or scope
   it to the user's own org.

Rebuild it on a schedule (nightly is plenty) and ship it as a data file. The index
for a 3,500-term corpus is under a megabyte of JSON.

**The generated index is a data artifact, not source.** Do not commit it — it is a
compact map of your internal vocabulary, which is exactly the kind of thing that
should not be in a repo that might one day be mirrored somewhere. `.gitignore` it,
build it in CI or at install time.

---

## Two hard-won details in the matcher

**Possessives.** Whisper emits TrueCase, punctuation, and possessives — so the
garble that reaches you is `Kubernetti's`, not `kubernettis`. An early guard read
"token contains an apostrophe → it's a contraction, skip it", which skipped exactly
the case we needed to fix. The rule that works: drop apostrophes rather than
splitting on them, so `Kubernetti's → kubernettis → KBRNTS → Kubernetes`, while a
**list of genuine contractions** (`what's`, `don't`, …) is skipped explicitly.

> Test on real Whisper output, not idealised lowercase strings. Its formatting is a
> feature to preserve; its garbles are the target.

**Inflections.** `/usr/share/dict/words` contains base lemmas and is missing most
plurals, possessives, and verb forms. So `docs`, `apps`, `reads`, `tags` all looked
out-of-vocabulary and became eligible for a phonetic swap — producing
`docs → DAGs`, `apps → APIs`, `reads → Redis`. In a repo full of Kubernetes
documentation that is a catastrophe, because those are the most common words in
the corpus.

The fix is `_deinflect()`: before declaring a token OOV, strip plural `-s/-es/-ies`
and verb `-ed/-ing` endings and re-check the dictionary. Genuine garbles
(`graphana`, `kubernetis`, `promethius`) do not reduce to a dictionary word, so
they stay correctable.

For a fleet, `/usr/share/dict/words` (~235k words, present on every Mac) is
adequate but crude. A frequency-ranked word list gives better control — you can
require that a token be *reasonably common* before treating it as a real word,
which catches the inverse failure where an obscure dictionary entry shields a
garble from correction.

---

## Phrase-repeat collapse

The second guard against whisper decode loops (see `01`, `-mc 0`). It collapses an
immediately-repeated multi-word unit to a single copy, comparing on normalised
tokens but keeping the **first occurrence verbatim** with its original casing and
punctuation.

The trigger is deliberately conservative — collapse only when it is almost
certainly an artifact and not ordinary speech:

- any unit repeated **≥ 3 times** (a loop), or
- a unit of **≥ 3 words** repeated back to back (a verbatim echo).

A two-word phrase repeated exactly twice is left alone. "No, no" is a thing people
say.
