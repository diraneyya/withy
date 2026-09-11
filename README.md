# Whisperbar

**Push-to-talk dictation for macOS that runs entirely on your machine.**
Hold a key, speak, let go — the text is typed into whatever app has focus.
Nothing is uploaded, nothing is transcribed in a datacentre, and there is no
per-seat licence.

```
   ┌──────────┐   hold key   ┌─────────┐   ┌──────────┐   ┌────────┐
   │ menubar  │─────────────▶│ record  │──▶│ whisper  │──▶│ clean  │
   │    🎙     │◀── release ──│ (local) │   │ (local)  │   │ up     │
   └──────────┘              └─────────┘   └──────────┘   └───┬────┘
        ▲                                                     │
        │ history, vocabulary, record key           types into ▼
        └──────────────────────────────────── whatever has focus
```

---

## Install

```bash
git clone https://github.com/diraneyya/whisperbar.git
cd whisperbar
./install.sh
```

Then grant **Hammerspoon** *Accessibility* and *Input Monitoring* in
System Settings → Privacy & Security, hold **right Option**, and speak.

Or hand the whole job to a coding agent — paste this at it:

> Install Whisperbar on my Mac by following
> https://raw.githubusercontent.com/diraneyya/whisperbar/master/LLM.md

Requires macOS with [Homebrew](https://brew.sh). About 4 GB of models. No Python
environment to manage — it runs on the Python that ships with macOS and has no
third-party Python dependencies at all.

---

## Why this exists

|  | Cloud dictation (Willow, Wispr Flow, …) | Whisperbar |
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
Wispr Flow take. So Whisperbar defaults to **right Option** and lets you move it.

That is deliberate: install Whisperbar on a different key from whatever you use
today, and compare them on the same sentences before you commit. To switch to
`fn` later, turn off the incumbent, set System Settings → Keyboard →
*Press 🌐 to: Do Nothing*, and pick `fn (globe)` from the menu.

### The vocabulary file

`~/.config/whisperbar/vocabulary.txt` — one flat list of the words a speech
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
in is not a rules problem, so Whisperbar runs the transcript through a small
local language model (via Ollama) that may **only reformat**:

```
spoken     let's meet on Monday no scratch that let's meet on Tuesday at three
typed      Let's meet on Tuesday at three.

spoken     ...like a child going to mama saying oh mama I hate it this is so stupid
typed      ...like a child going to mama saying, "Oh mama, I hate it. This is so
           stupid."
```

A small model given an open brief will rewrite meaning. The defence is not a
better prompt — it is a **gate**:

> Every word in the output must be a word that was spoken in this dictation, a
> term from your vocabulary file, or a list marker. If the model invents a word,
> the entire output is thrown away and the plain transcript is typed instead.

So the worst case is not corruption. It is that formatting quietly doesn't
happen. That asymmetry is the design. Turn the whole stage off from the menubar
if you would rather have the raw words.

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
| `whisperbar/` | the pipeline — capture, transcribe, correct, format, inject, history |
| `Whisperbar.spoon/` | the Hammerspoon front end: record key, menubar, watchdog |
| `install.sh` | installer, idempotent, appends to an existing Hammerspoon config |
| `LLM.md` | the same install as instructions for a coding agent |
| `eval/` | measures the clean-up stage against a corpus of real dictations |
| `docs/` | the design rationale, and **every failure mode already paid for** |

`docs/05-gotchas.md` is the one worth reading before you change anything:
zero-byte WAVs with exit code 0, hotkeys that silently stop working, long
dictations arriving truncated, destroyed clipboards.

### Command line

Whisperbar is a menubar app and you never need this, but it exists — the Spoon
drives it, and it makes every stage testable without a microphone:

```bash
whisperbar diagnose              # check the install
whisperbar diagnose --mic        # also measure microphone start latency
whisperbar run --text "..." --dry   # run the text stages, print, don't type
whisperbar run take.wav --dry    # run a recording through the whole pipeline
whisperbar history               # what you have dictated
whisperbar mics                  # input devices, and which one is selected
```

---

## Licence

Apache-2.0. Chosen over MIT for the explicit patent grant, which is the question
that comes up when someone installs a tool on a work laptop.
