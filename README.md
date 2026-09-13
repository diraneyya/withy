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

<p align="center">
  <em>withy</em> &nbsp;/ˈwɪði/&nbsp; — rhymes with <em>smithy</em><br>
  <sub>a willow branch cut for weaving</sub>
</p>

<p align="center">
  <img src="docs/willows.jpg" alt="Weeping willows along the water" width="45%">
  <img src="docs/withies.jpg" alt="Cut willow rods laid out on a garden path" width="45%">
</p>

<p align="center">
  <sub>The weeping willows on the water, and withies cut and sorted for
  weaving — Almere Buiten</sub>
</p>

---

## Install

```bash
git clone https://github.com/diraneyya/withy.git
cd withy
./install.sh
```

Then grant **Hammerspoon** *Accessibility* and *Input Monitoring* in System
Settings → Privacy & Security, hold **right Option**, and speak.

Or hand the whole job to a coding assistant — paste this at it:

> Install Withy on my Mac by following
> https://raw.githubusercontent.com/diraneyya/withy/master/LLM.md

That path is worth preferring: the assistant can see which tools already exist
on your machine, offer you a real choice of them, and configure the installer
for you, so you never have to discover or type a command.

Requires macOS with [Homebrew](https://brew.sh). No Python environment to
manage — it runs on the Python that ships with macOS and has no third-party
Python dependencies at all.

---

## Using it

**Hold the record key, speak, release.** That is the whole interface. The
willow in your menu bar turns red while recording, amber while transcribing and
blue while it tidies the text, and a small banner in the corner of the screen
says the same thing so you never have to look up.

Everything else lives in that menu:

| | |
|---|---|
| **Recent dictations** | click to copy; *Type again*, *Copy unformatted*, *Redo from audio* |
| **Record key** | fn, right ⌥, right ⌘, right ⇧, right ⌃, left ⌥ |
| **Polishing LLM** | off, a local model, a local CLI, or a remote API |
| **Speech model** | whichever you have; eight more downloadable from the menu |
| **Edit vocabulary** | words a speech model would otherwise get wrong |
| **Edit polishing instructions** | how it should write |

### The record key

The default is **right Option, not fn**. `fn` is the nicer key to hold, and it
is also the one macOS binds to Apple Dictation and the one most commercial
dictation tools take — so Withy stays out of its way by default.

That is deliberate: install Withy on a different key from whatever you use
today and compare them on the same sentences before committing. To move to `fn`
later, turn off the incumbent, set System Settings → Keyboard → *Press 🌐 to: Do
Nothing*, and pick it from the menu.

---

## What it does that other dictation tools don't

**Keep talking while it catches up.** Release the key and immediately press it
again — the previous take transcribes and polishes while you record the next
one. Dictating is not gated on the machine finishing.

**Re-run a dictation without saying it again.** The audio is kept, so *Redo from
audio* runs the whole pipeline again on the same recording. Change the speech
model, or the polishing backend, or the instructions, and redo it — that is a
controlled comparison on identical audio, which is the only honest way to tell
whether a setting is actually better. Nothing that discards your audio can do
this.

**Write the polishing instructions yourself.** The prompt is a file you edit
(menu → *Edit polishing instructions…*). Want no em-dashes, British spelling,
bullets instead of prose, a house style? Say so, in your own words.

**Your words stay your words.** Whatever model tidies the text, its output is
checked against what you actually said: it may add punctuation, paragraphs,
quotes and lists, and drop filler and retracted phrases — but a word you did not
say cannot survive into the result. The formatting is negotiable; the content is
not.

**Nothing is lost.** Every dictation is written to history *before* Withy tries
to type it, so a wrong window, a lost keystroke or a crash costs you a click,
not a paragraph.

---

## Unopinionated by design

Withy tries not to decide things for you, and to say plainly what each choice
costs.

### Polishing

Speech has no punctuation, paragraphs or quotation marks. Filling those in —
and applying spoken self-corrections like *"no, scratch that"* — is the one
place Withy uses a language model, and you choose which, or none:

| | Speed | Leaves your Mac | Needs |
|---|---|---|---|
| **Off** | instant | no | nothing |
| **Local LLM model** | seconds | **no** | Ollama and a model (~2 GB) |
| **Local CLI** | slower | depends on the tool | an assistant you already have |
| **Remote OpenAI API** | fast | **yes** | your API key |
| **Remote Anthropic API** | fast | **yes** | your API key |

The *local CLI* option exists because a work machine often already provides a
licensed assistant, so polishing can use it and nobody has to hand out an API
key. Any command that takes a prompt on standard input and prints the answer
works; Withy checks the one you give it and tells you if it is wrong, rather
than quietly doing nothing.

The menu says *"leaves this Mac"* on the remote options, because that is the one
thing worth knowing before you pick one.

### Models

Both model choices are yours, and both are discovered rather than assumed.
**Speech models** are found on disk — anything you drop into the whisper-cpp
folder is offered — and eight common ones can be downloaded from the menu, from
a 74 MB English-only model up to the most accurate one. The `-q5_0` entries are
the same weights quantised: roughly a third of the size and correspondingly
faster, for a small accuracy cost.

The **local LLM model** is optional. The installer does not download one unless
asked, and it can be added or removed from the menu afterwards. If you have not
installed it, the menu says so and offers to — it never appears as a choice that
silently does nothing.

### Your vocabulary

`~/.config/withy/vocabulary.txt` — project names, products, acronyms,
colleagues' names. Space- or newline-separated.

Keep it to proper nouns, and keep it short. A long list does more harm than
good: the more entries there are, the more likely an ordinary word you said
collides with one of them. A short list also does something useful beyond
spelling — it is what allows the polishing model to repair a garbled attempt at
one of your terms, and to refuse when the word is not yours to correct.

---

## When something goes wrong

**The text went into the wrong window.** It is not lost. Menu → *Recent
dictations* → click to copy, or *Type again* to type it wherever your cursor is
now. This is the most common problem, because transcription takes a moment and
focus can move in that moment.

**Nothing was typed at all.** Either no speech was detected — Withy stays silent
rather than typing something you did not say — or typing failed, in which case
the text is in history and `/tmp/withy.log` says why.

**The transcription was wrong.** *Redo from audio* re-runs it. If a particular
word is always wrong, add it to your vocabulary. If it is wrong in a way a
better model would fix, change the speech model and redo the same audio to
check.

**The first word or two got clipped.** The microphone takes a moment to open.
The chime is the cue — speak after it, not as you press. `withy diagnose --mic`
measures the gap on your machine.

**The punctuation is missing.** The polishing model's output is discarded when
it fails a safety check, and the plain transcript typed instead; the log gives
the reason. Or polishing may simply be off, or pointed at a backend that is not
working — the menu shows which.

**Nothing happens when you press the key.** Usually Hammerspoon is missing
*Input Monitoring*. Grant it, then menu → *Reload*. `withy diagnose` checks the
rest of the install.

**Pressing the key again cancelled my recording.** That is deliberate — a new
press discards a take still in progress, so you can cancel and re-speak without
a second key. A take you already *finished* is safe, and is in history.

---

## Under the hood

| Path | |
|---|---|
| `withy/` | the pipeline — capture, transcribe, correct, polish, inject, history |
| `Withy.spoon/` | the Hammerspoon front end: record key, menu bar, banner |
| `install.sh` | installer; idempotent, appends to an existing Hammerspoon config |
| `LLM.md` | install and support instructions written for a coding assistant |
| `docs/` | design notes, and every failure mode already paid for |

There is a command line — the menu bar drives it and you never need it, but it
makes every stage testable without a microphone:

```bash
withy diagnose            # check the install
withy models              # speech and polishing models available
withy history             # what you have dictated
withy run --text "..." --dry    # run the text stages, print, don't type
withy purge 7             # keep the last week, delete the rest
```

Your dictations and recordings stay in `~/.local/share/withy/`, your settings
and vocabulary in `~/.config/withy/`. Nothing is sent anywhere unless you pick a
remote polishing backend.

---

## The name

A **withy** is a willow branch cut for weaving.

This was written in a garden in Almere Buiten, in front of a heap of willow
branches a neighbour had cut down the day before. The tree is gone now — the one
whose long strands you could lie under on summer nights by a fire and watch
moving against the sky. What is left is a pile of cut branches and the question
of what to do with them.

The traditional answer is that you weave them. Withies become baskets, fences,
screens; the tree goes on being useful in another shape. That seemed like a fair
description of a tool that takes speech — which is loose, disordered, and
disappears the moment it is made — and weaves it into something that holds.

It is also, plainly, a free local alternative to the dictation tools people pay
per seat for. But it is named after the tree, not after them.

---

## Licence

Apache-2.0. Chosen over MIT for the explicit patent grant, which is the question
that comes up when someone installs a tool on a work laptop.
