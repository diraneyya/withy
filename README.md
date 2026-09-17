<p align="center">
  <img src="docs/logo.png" alt="" width="132">
</p>

<h1 align="center">Withy Voice</h1>

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
Settings → Privacy & Security, hold **right Option**, and speak. Requires macOS
with [Homebrew](https://brew.sh); no Python environment to manage.

Or hand the whole job to a coding assistant — paste this at it:

> Install Withy Voice on my Mac by following
> https://raw.githubusercontent.com/diraneyya/withy/master/LLM.md

**Updating:** `withy update`, or *Update Withy Voice…* in the menu. Every choice
you have made is kept.

---

## Why you might want it

**It is free, in the sense that matters.** Not a trial, not a seat, not a plan
you lose access to your own words without. If you use a hosted model to tidy the
text you pay for those tokens and nothing else — no margin on top, and you can
change provider, run a local model instead, or switch polishing off entirely and
still have a working tool.

**It is private if you want it to be.** Speech recognition is always local. The
tidying step is the only part that can leave your machine, it is your choice
whether it does, and there is an offline switch that guarantees it doesn't.

**Your words cannot be rewritten.** Whatever model tidies the text, its output
is checked against what you actually said. It may punctuate, paragraph, quote
and list, and it may drop filler and a phrase you visibly replaced — but a word
you did not say cannot reach the screen. The formatting is negotiable; the
content is not.

**Your vocabulary is a text file.** Names, jargon, product names — the words
speech recognition mangles — live in a list you can read, diff, and copy to
another machine. Not a database, not a settings pane.

**You can read the instructions it sends, and change them.** The prompt is a
file. Want British spelling, no em-dashes, shorter paragraphs? Say so, in your
own words. And `withy prompt test` runs your version against a suite of real
cases so you can tell whether you improved it or broke it — the same suite that
gates changes to the shipped one.

**Editing it doesn't freeze it.** Withy remembers the instructions it last gave
you, so an update can tell your edits from its own old defaults: untouched, it
updates silently; edited elsewhere, both changes survive; edited in the same
place, it asks you and shows what each version does.

**You can keep talking while it catches up.** Release the key and press again —
dictations queue, and the banner stack shows you what is recording, what is
waiting and what is being worked on. Results are typed in the order you spoke
them, never the order they happen to finish.

**Nothing is hidden.** Which model is in use, how fast each one is *on your
machine* (`withy benchmark`), what your vocabulary contains and where each term
came from, what the polishing step was told, and every dictation you have made —
all inspectable, all yours.

---

## What it is honest about

**It is a prototype, and it is built on [Hammerspoon](https://www.hammerspoon.org).**
That is why the permissions you grant are to Hammerspoon rather than to an app
called Withy, and why there is no signed bundle in the menu bar of its own. It
was written quickly, with an LLM, by someone who wanted it to exist — and it
works, every day, as the tool its author dictates with.

**It is slower than the commercial ones.** Transcription runs on your CPU, so
there is a pause after you let go that a paid tool with a datacentre behind it
does not have. The queue makes that pause livable rather than absent. Pointing
it at a transcription server you control is the obvious next step and is not
built yet.

**The polishing is good, not perfect.** It is a prompt and a safety check, both
of which are visible to you and both of which you can change — which is rather
the point.

**It is macOS only**, and there is no Windows or Linux port planned.

---

## Using it

**Hold the record key, speak, release.** That is the whole interface. The willow
in your menu bar and a small banner in the corner say what is happening.

Everything else lives in that menu:

| | |
|---|---|
| **Recent dictations** | click to copy; *Type again*, *Copy unformatted*, *Redo from audio* |
| **Record key** | fn, right ⌥, right ⌘, right ⇧, right ⌃, left ⌥ |
| **Polishing LLM** | off, a local model, a local CLI, or a remote API |
| **Speech model** | whichever you have; more downloadable from the menu |
| **Edit vocabulary** | words a speech model would otherwise get wrong |
| **Polishing instructions** | how it should write — edit, test, or check for updates |

The default record key is **right Option, not fn** — `fn` is the nicer key to
hold, and it is also the one macOS and most commercial dictation tools take, so
Withy stays out of its way until you choose otherwise. Install it on a different
key from whatever you use today and compare them on the same sentences.

**For organisations:** terms everyone needs — internal tools, product names —
can be shipped with the code in `withy/vocabulary.d/` rather than typed into
every config file. A fork adds its own file there and keeps merging cleanly from
upstream. `withy vocab` always shows the user every term and where it came from.

**Everything else** — troubleshooting, how the pieces fit together, the design
decisions and why each rule exists — is in [`LLM.md`](LLM.md) and
[`CLAUDE.md`](CLAUDE.md), written to be read by a person or handed to an
assistant.

---

## The name

A **withy** is a willow branch cut for weaving.

Withy Voice was written in a garden in Almere Buiten, beside a heap of willow branches
a neighbour had cut down the day before. The tree itself is gone — the one whose
long strands used to move against the sky above a summer fire. What remains is a
pile of rods and the question of what to do with them.

The traditional answer is to weave them. Withies become baskets, fences and
screens; the tree goes on being useful in another shape. It is a fair
description of a tool that takes speech — loose, disordered, and gone the moment
it is made — and weaves it into something that holds.

It is also, plainly, a free local alternative to the dictation tools people pay
per seat for. But it is named after the tree, not after them.

---

## Licence

Apache-2.0. Chosen over MIT for the explicit patent grant, which is the question
that comes up when someone installs a tool on a work laptop.
