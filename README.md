<p align="center">
  <img src="docs/logo.png" alt="" width="132">
</p>

<h1 align="center">Withy</h1>


<p align="center">
  <strong>Push-to-talk dictation for macOS that runs entirely on your machine.</strong><br>
  Hold a key, speak, let go — the text is typed into whatever app has focus.<br>
  Nothing is uploaded, nothing is transcribed in a datacentre,<br>
  and there is no per-seat licence.
</p>

---

## The name

A **withy** is a willow branch cut for weaving.

This was written in a garden, in front of a heap of willow branches a neighbour
had cut down the day before. The tree is gone now — the one whose long strands
you could lie under on summer nights by a fire and watch moving against the
sky. What is left is a pile of cut branches and the question of what to do with
them.

The traditional answer is that you weave them. Withies become baskets, fences,
screens; the tree goes on being useful in another shape. That seemed like a
fair description of a tool that takes speech — which is loose, disordered, and
disappears the moment it is made — and weaves it into something that holds.

It is also, plainly, a free local alternative to the cloud dictation tools
people pay per seat for. But it is named after the tree, not after them.

---

## Install

```bash
git clone https://github.com/diraneyya/withy.git
cd withy
./install.sh
```

Then grant **Hammerspoon** *Accessibility* and *Input Monitoring* in
System Settings → Privacy & Security, hold **right Option**, and speak.

Or hand the whole job to a coding agent — paste this at it:

> Install Withy on my Mac by following
> https://raw.githubusercontent.com/diraneyya/withy/master/LLM.md

Requires macOS with [Homebrew](https://brew.sh). About 4 GB of models. No Python
environment to manage — it runs on the Python that ships with macOS and has no
third-party Python dependencies at all.

---

## Why this exists

|  | Cloud dictation (Willow, Wispr Flow, …) | Withy |
|---|---|---|
| Per-seat cost | ~$10–15/user/month | none |
| Audio leaves the device | every utterance | never |
| Works offline / on a plane | no | yes |
| Custom vocabulary | vendor dictionary UI | a text file you own |
| Procurement, DPA, security review | required | not required |

The privacy column is usually what actually unblocks the decision. A dictation
tool sees *everything a person writes* — code, incident notes, customer names,
unreleased plans. Running the model locally removes that conversation entirely.

The underlying technology is free and MIT-licensed (whisper.cpp, the Whisper
weights). What no vendor has an incentive to do is assemble it and give it away.
That is all this is.

---

## Using it

**Hold the record key, speak, release.** That is the whole interface.

The **🎙 menubar icon** holds everything else:

- **Recent dictations** — click one to copy it. Each has *Type again*,
  *Copy unformatted*, and *Redo from audio* for when a transcription came out
  wrong. Nothing you dictate is ever lost, even if the typing lands in the wrong
  window.
- **Record key** — fn, right ⌥, right ⌘, right ⇧, right ⌃, left ⌥.
- **Clean up wording** — the formatting pass, on or off.
- **Edit vocabulary…** — opens your word list.

### The record key, and why the default is not `fn`

`fn` (globe) is the best key to hold: bottom-left, findable by feel, no chord.
It is also the key macOS binds to Apple Dictation, and the one Willow Voice and
Wispr Flow take. So Withy defaults to **right Option** and lets you move it.

That is deliberate: install Withy on a different key from whatever you use
today, and compare them on the same sentences before you commit. To switch to
`fn` later, turn off the incumbent, set System Settings → Keyboard →
*Press 🌐 to: Do Nothing*, and pick `fn (globe)` from the menu.

### The vocabulary file

`~/.config/withy/vocabulary.txt` — one flat list of the words a speech
model gets wrong. Project names, products, acronyms, colleagues' names.

```
# separated by spaces or newlines, # starts a comment
Kubernetes PagerDuty Grafana
OrwaTech Kleinanzeigen
```

It does three jobs: biases the speech model toward those spellings, fixes
spacing garbles deterministically (`pager duty` → `PagerDuty`), and — the
interesting one — **licenses the clean-up model to repair a garbled attempt at
one of your terms**. Measured, on a real dictation:

```
heard:              "we use Homebro ... install Hammerspoon and Olama"
no vocabulary:      unchanged      (the fix is proposed, then refused)
with vocabulary:    "we use Homebrew ... install Hammerspoon and Ollama"
```

**Keep it short — tens of terms, not thousands.** See below for why.

---

## How the text gets cleaned up

Speech has no punctuation, no paragraphs, and no quotation marks. Filling those
in is not a rules problem, so Withy runs the transcript through a small
local language model (via Ollama) that may **only reformat**:

```
spoken     let's meet on Monday no scratch that let's meet on Tuesday at three
typed      Let's meet on Tuesday at three.

spoken     ...like a child going to mama saying oh mama I hate it this is so stupid
typed      ...like a child going to mama saying, "Oh mama, I hate it. This is so
           stupid."
```

A small model given an open brief will rewrite meaning. The defence is not a
better prompt. The model's output is **aligned against what you actually said**
and taken word by word:

| | |
|---|---|
| words that match | the model's version — this is where the punctuation, casing and quotes come from |
| words it deleted | allowed; removing filler and retracted text is the point |
| words it inserted | refused, unless they are vocabulary terms or list markers |
| words it swapped | reverted to what you said, unless every token is a vocabulary term |

**No word can be replaced by one you never said** — and unlike an
accept-or-reject gate, one bad word no longer costs you the formatting of the
whole paragraph. (It did, before this was measured: the model corrected "y'all"
to "your", and that single word discarded the capitalisation and quotation
marks for an entire dictation.)

Two further checks sit on top, because word-level safety is not the only way
this can go wrong:

- **Degenerate formatting is rejected.** A small model that loses the thread
  emits one comma per word — `ones, maybe, some, other, issue, will, happen,` —
  which passes a word check perfectly, since every word *was* spoken. Comma and
  line density are checked against what prose actually looks like.
- **Capitalising the first letter is deterministic**, never the model's job, so
  it happens even when a chunk is discarded.

Turn the whole stage off from the menubar if you would rather have the raw
words.

---

## Silence

Whisper hallucinates on silence. Fed a second of room tone it returns a
confident **"Thank you."** — and a dictation tool that types "Thank you." when
you said nothing is worse than one that does nothing.

The obvious fix is a loudness threshold, and it is the wrong one: a level tuned
for a quiet room rejects real speech in a garden and passes a fan in an office.
The noise floor is not a constant, so it cannot be in the test.

What separates speech from noise regardless of the floor is that **speech is
amplitude-modulated at the syllable rate** — loud bursts with real gaps between
them — while a fan, traffic and room tone hold a near-constant level. So Withy
measures the *spread* between loud and quiet frames, which is a ratio and
therefore floor-independent. Measured on real dictations:

```
real speech (13 takes)        spread 16.2 - 35.9 dB
"Thank you." on silence (2)   spread 10.3 and 10.5 dB
```

The threshold sits at 13 dB, and deliberately errs toward transcribing — typing
nothing when you spoke is the worse failure. Every measurement is logged so it
can be retuned against data rather than re-guessed.

---

## What was measured, and what got deleted

This started as the dictation half of a personal tool that had run daily since
May 2026. Before packaging it, every correction rule was measured against **360
real dictations**. Two of them were doing more harm than good and were removed:

**Phonetic proper-noun correction** — "swap an out-of-vocabulary word for the
corpus term with the same phonetic key". It fired 24 times and **damaged the
text 15 of those times**:

| spoken | typed | |
|---|---|---|
| gonna | Kuhn | ×3 |
| died | T8DE84EW | ×3 |
| cues | Gaza | |
| badass | Bytes | ×2 |

`metaphone("badass")` and `metaphone("Bytes")` are both `BTS`. Against a
3,000-term auto-derived index, almost any spoken word collides with something.
This is why the vocabulary file is short, hand-written, and yours: a list of
tens of terms has a collision surface small enough to be safe.

**Hedge removal** — deleting "sort of" and "kind of" as filler. Of 20 firings
sampled, *every one* was legitimate: "what **kind of** proof is needed", "the
**sort of** thing that deserves publishing". Those phrases almost always
introduce a noun of type, not a hedge.

Both now belong to the language model, which has the surrounding sentence and
can tell `a node` from `Anode`.

The general lesson, which is in `docs/` in more detail: **for a corrector,
precision beats recall.** A missed fix is visible and costs one keystroke. A
wrong fix is silent and ships.

---

## Layout

| Path | What it is |
|---|---|
| `withy/` | the pipeline — capture, transcribe, correct, format, inject, history |
| `Withy.spoon/` | the Hammerspoon front end: record key, menubar, watchdog |
| `install.sh` | installer, idempotent, appends to an existing Hammerspoon config |
| `LLM.md` | the same install as instructions for a coding agent |
| `eval/` | measures the clean-up stage against a corpus of real dictations |
| `docs/` | the design rationale, and **every failure mode already paid for** |

`docs/05-gotchas.md` is the one worth reading before you change anything:
zero-byte WAVs with exit code 0, hotkeys that silently stop working, long
dictations arriving truncated, destroyed clipboards.

### Command line

Withy is a menubar app and you never need this, but it exists — the Spoon
drives it, and it makes every stage testable without a microphone:

```bash
withy diagnose              # check the install
withy diagnose --mic        # also measure microphone start latency
withy run --text "..." --dry   # run the text stages, print, don't type
withy run take.wav --dry    # run a recording through the whole pipeline
withy history               # what you have dictated
withy mics                  # input devices, and which one is selected
```

---

## Licence

Apache-2.0. Chosen over MIT for the explicit patent grant, which is the question
that comes up when someone installs a tool on a work laptop.
