# local-dictation-blueprint

**A fully-local speech-to-text dictation pipeline — the architecture, the working
reference code, and every bug already paid for — so an engineering team can build
an in-house dictation tool instead of buying per-seat licences for a cloud one
(Willow Voice, Wispr Flow, and similar).**

This is not a product. It is a **blueprint extracted from a working system** that
has been in daily use on macOS since May 2026: push-to-talk → local Whisper →
deterministic correction → text typed into whatever app has focus. Multilingual
(English and Arabic verified live). No network call at any point in the transcribe
path.

The intended reader is **an engineer, or a coding agent working for one**, who has
been asked "can we just build this ourselves?" The answer is yes, and this repo is
the head start: the design is proven, and roughly 60% of the work in getting there
was discovering the failure modes documented in `docs/05-gotchas.md`.

---

## Why build instead of buy

| | Cloud dictation (Willow, Wispr Flow, …) | This |
|---|---|---|
| Per-seat cost | ~$10–15/user/month | $0 |
| Audio leaves the device | Yes — every utterance | **No** |
| Works offline / on a plane / in a SCIF | No | Yes |
| Custom vocabulary | Manual dictionary UI, per user | **Auto-derived from your own corpus** (repos, wikis, ticket titles) |
| Auditability | Vendor black box | Every stage is inspectable text |
| Procurement / DPA / security review | Required | Not required |

The privacy column is usually the one that actually unblocks the decision. A
dictation tool sees *everything a person writes* — code, incident notes, customer
names, unreleased plans. A local model removes that entire conversation.

**The technology is free; every product built on it is not.** whisper.cpp, ggml,
and OpenAI's Whisper weights are all MIT — the hard part, the part that took a
research lab, costs nothing. But no packaged dictation tool gives it away
unlimited: the local ones cap a free tier and then ask for a licence, the genuinely
free open-source one only writes to the clipboard rather than typing into the
focused field, and the one unlimited free option is Apple's built-in Dictation,
which has no custom vocabulary. Nobody is giving this away, because there is no
business model in doing so.

So you are not competing with a free product. You are assembling free components
that no vendor has an incentive to assemble for free — and your incentive is
different from theirs, because you are not selling it. `docs/07-landscape.md` has
the full picture, including the cases where you should buy instead.

---

## The pipeline in one diagram

```
  ┌──────────────┐   hold key    ┌───────────────┐   16 kHz mono WAV
  │ hotkey layer │──────────────▶│ audio capture │──────────────────┐
  │  (PTT / VAD) │◀── release ───│   (ffmpeg)    │                  │
  └──────────────┘               └───────────────┘                  │
                                                                    ▼
                        ┌───────────────────────────────────────────────────┐
                        │ STAGE 1  language detect   whisper-cli -dl        │
                        │ STAGE 2  transcribe FORCED whisper-cli -l <lang>  │
                        │          (+ vocabulary bias --prompt, en only)    │
                        └───────────────────────┬───────────────────────────┘
                                                │ raw transcript
                        ┌───────────────────────▼───────────────────────────┐
                        │ STAGE 3  deterministic correction (no model)      │
                        │   a. filler + stutter removal                     │
                        │   b. phrase-repeat collapse (whisper loop guard)  │
                        │   c. corpus proper-noun swaps (3 precision rules) │
                        └───────────────────────┬───────────────────────────┘
                                                │ final text
                  ┌─────────────────────────────┴─────────────────────────┐
                  ▼                                                       ▼
        ┌───────────────────┐                                  ┌────────────────────┐
        │ STAGE 4  inject   │  short → synthetic keystrokes    │ STAGE 5  history   │
        │ into focused app  │  long  → clipboard paste+restore │ append-only JSONL  │
        └───────────────────┘                                  └────────────────────┘
```

Every arrow is local. The only thing that ever touched a network in the original
system was a *separate* feature (an LLM answering questions about a notes corpus),
which is deliberately **out of scope here** — see `docs/01-pipeline.md` §"What was
cut".

---

## What's in here

| Path | What it is |
|---|---|
| `docs/01-pipeline.md` | Stage-by-stage spec of the transcribe pipeline, with the exact flags and why each one is there |
| `docs/02-capture.md` | Audio capture and the push-to-talk layer — the parts that are macOS-specific and how to port them |
| `docs/03-correction.md` | The deterministic correction engine: what it fixes, what it deliberately refuses to fix, and the precision-over-recall argument |
| `docs/04-injection.md` | Getting text into the focused application without losing it |
| `docs/05-gotchas.md` | **Read this one.** Every failure mode hit in production, with symptom → root cause → fix |
| `docs/06-plugin-spec.md` | How to package this for a company: the two scopes, the deployment model, the security review answers |
| `docs/07-landscape.md` | Competitors, licences, and the build-vs-buy maths done honestly |
| `reference/` | Working, de-personalised reference implementation (Python + bash + Lua) |
| `CLAUDE.md` | Orientation for a coding agent asked to build the plugin from this repo |

---

## Try the reference implementation in 5 minutes

```bash
brew install whisper-cpp ffmpeg
# ~1.6 GB, the accuracy/speed sweet spot on Apple Silicon:
curl -L -o ~/.local/share/whisper/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

pip install jellyfish            # only needed for corpus vocabulary correction

cd reference
export DICTATION_MODEL=~/.local/share/whisper/ggml-large-v3-turbo.bin

# transcribe a file
python3 -m dictation transcribe /path/to/some.wav

# record from the mic, transcribe, correct, print (no typing)
./record.sh /tmp/take.wav          # Ctrl-C to stop
python3 -m dictation run /tmp/take.wav --dry
```

### Seeing the correction stage work

Build a vocabulary index from this repo's own docs, then run text through it. All
output below is real, not illustrative:

```bash
export DICTATION_CORPUS=$PWD/../docs
python3 -m dictation build-vocab
# 362 index entries → ~/.local/share/dictation/vocab_index.json
# 120 bias terms    → ~/.local/share/dictation/vocab_prompt.txt

python3 -m dictation correct --text \
  "um so the the plan is you know to deploy uh kubernetis behind pager duty and the ess ell oh"
#   removed: ['you know', 'um', 'the', 'uh']
#   [oov-metaphone] 'kubernetis' → Kubernetes
#   [concat-exact]  'pager duty' → PagerDuty
#   [spoken-letter] 'ess ell oh' → SLO
# so the plan is to deploy Kubernetes behind PagerDuty and the SLO
```

And the safety property, which matters more than the fixes — run a sentence
containing none of the corpus terms:

```bash
python3 -m dictation run /opt/homebrew/share/whisper-cpp/jfk.wav --dry
```

The index built this way contains `Node` (it appears throughout the docs as an
example), and the JFK sample says *"ask **not** what your country can do for you"*.
`metaphone("not")` is `NT`; so is `metaphone("Node")`. A recall-maximising matcher
swaps that word — the first implementation of this stage did exactly that. This one
returns the transcript **byte-identical, zero swaps**; verify with
`dictation history show 1`, which prints `raw` and `final` side by side.

That is the property the whole design in `docs/03-correction.md` exists to protect,
and it is why `page duty` is left alone in the example above while `pager duty` is
corrected: the joined form has to match a corpus term *exactly*, and "pageduty"
does not.

Measured on an M2 Pro / 16 GB with `large-v3-turbo`, on the `jfk.wav` sample that
ships with the Homebrew formula: an 11-second clip takes **~5.5 s** end to end,
of which most is loading the 1.6 GB model **twice** — once per pass. Actual
inference is ~1.7 s. Keeping the model resident (whisper-server, or linking
`libwhisper`) removes that overhead and is the first optimisation any production
build should make. Correction is sub-millisecond.

---

## Status and provenance

Extracted from a personal tool (`brain-voice`) that has run daily since 2026-05.
The dictation path described here is **in production use**; the packaging in
`docs/06-plugin-spec.md` is a **specification, not shipped code** — it is written
to be implemented, and says so wherever it is speculating.

Personal corpus data, personal file paths, and the notes-assistant half of the
original tool have been removed. Nothing in `reference/` reads anything outside the
paths you configure.
