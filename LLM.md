# Withy Voice — instructions for an AI assistant

You are helping someone install, configure, or use **Withy Voice**: local push-to-talk
dictation for macOS. Hold a key, speak, release, and the text is typed into
whatever app has focus.

This document is the whole task. Part 1 is installation. **Part 2 is a FAQ** —
after installing, stay available and answer from it rather than guessing, because
most of what people ask has a specific answer that is not discoverable from the
UI.

Source: <https://github.com/diraneyya/withy>

---

# Part 1 — Installation

## Before you start, tell the user

- this downloads about 2–4 GB (a speech model, and a language model if they
  choose on-device polishing)
- it installs Homebrew packages: `whisper-cpp`, `ffmpeg`, `hammerspoon`, and
  optionally `ollama`
- at the end **they** must grant permissions by hand; you cannot do it for them
- it will not disturb an existing Hammerspoon setup — it appends one line

Then ask them to confirm. Do not start a multi-gigabyte download without a yes.

## ⭐ Your job BEFORE running the installer

**Work out the polishing options on this machine and let the user choose one.
Then pass the answer to the installer.** The user should never have to discover
or type a command.

This is the split: **you** have context about this specific computer and the
tools on it — which agents are installed, what the company provides, what you
are yourself running under. The installer is a deterministic script and knows
none of that. So you do the discovery and the judgement; it does the execution.

### 1. Find what is installed

```bash
for c in claude llm ollama codex cursor-agent copilot gemini q; do
  command -v "$c" >/dev/null && echo "found: $c"
done
```

Also use what you already know. If you are running inside a corporate assistant,
you likely know which tools that organisation provides — say so rather than
making the user hunt.

### 2. Use what you know, and measure what you find

The probe above only finds names you thought to look for. **You very likely know
about command-line AI assistants that are not in that list** — ones specific to
this organisation, ones released after that list was written, ones you are
running under right now. Use that knowledge; it is the main reason a human is
not doing this step.

Two things to work out for each candidate:

**The non-interactive form.** Withy needs a command that takes a prompt on
standard input and prints the answer to standard output. For most assistants
that is `-p` (or `--print` / `--prompt`). Some are wrappers that proxy several
underlying agents — if you find one, use its own listing command to enumerate
what it offers, and turn each into a concrete runnable command rather than
presenting the wrapper itself as the answer.

**How long it actually takes.** This is the part that cannot be reasoned about:

```bash
withy set-command "<candidate>"
withy test-command
```

`test-command` runs the command exactly as Withy will and reports the elapsed
time, along with whether it errored or printed a banner around the answer. Try
each plausible candidate and keep the fastest that returns clean text. Polishing
runs on every dictation, so a few seconds of difference is the difference
between a tool someone keeps and one they turn off.

**Do not assume a smaller or "faster" model is quicker.** Measured on one
machine with the same audio, the default model took 4.5-7.5 s while the same
command with a small-model flag took 33.5-51.9 s. Through a CLI, model choice
interacts with process startup, caching and routing in ways that do not follow
from the model's size. Measure; do not predict.

### 3. Offer the user a real choice

Present two to four concrete options with a recommendation and the trade-off —
not a list of binaries. For example:

> I found two ways to polish your dictation on this machine:
>
> 1. **`claude -p`** — uses an assistant already installed here. No API key,
>    nothing to download, and it answered a test prompt in 4 seconds.
>    *Recommended.*
> 2. **`gemini -p`** — also installed, took 9 seconds on the same test.
>
> There is also a local model (a ~2 GB download, private but slower and less
> good at paragraphs), or a remote API if you have your own key. Which would
> you like?

If nothing suitable is installed, say so and offer the alternatives instead of
inventing a command.

### 4. Check the choice, then hand it to the installer

```bash
./install.sh --polish-command "claude -p"
```

The installer stores it and runs `withy test-command` itself, which exercises
the command exactly as Withy will and reports whether it is missing, errors, or
prints a banner around the answer. **Read that output** — a command that fails
this check leaves polishing silently doing nothing.

Other shapes: `--polish-backend off` (no polishing), `--with-llm` (also install a
local LLM model), `--polish-backend openai` (then set a key).

**Do not guess at a fast-model flag.** A smaller model is not reliably faster
through a CLI — measured on Claude Code with the same audio, `claude -p` took
4.5-7.5 s while `claude -p --model haiku` took 33.5-51.9 s. Start with the plain
command, and if it is slow, try a flag and **measure it** with
`withy test-command`, which reports the elapsed time.

---

## Install

```bash
git clone https://github.com/diraneyya/withy.git
cd withy
./install.sh
```

**Ask before installing the on-device model.** `./install.sh --no-llm` skips
Ollama entirely and saves a ~2 GB download; polishing can still use a local CLI
or a hosted API, or be turned off. It can be added later from the menu, and
removed from there too — nothing about this choice is permanent. See "Do they
want on-device polishing?" below.

`--model base.en` is the low-resource speech model — much faster, noticeably
less accurate, English only.

The installer is idempotent. If a step fails, fix the cause and re-run it; do
not attempt the steps by hand.

## Verify — do not skip this

```bash
~/.local/bin/withy diagnose
~/.local/bin/withy run --text "um so the the plan is to test this" --dry
```

The second must print a cleaned, punctuated sentence. If it prints the input
unchanged, polishing is not reaching a model. **Report what the command actually
printed.** Never tell the user it works because a command exited 0.

## The part you cannot do

> Open **System Settings → Privacy & Security**, and under **Accessibility** and
> **Input Monitoring**, switch on **Hammerspoon**. The microphone is requested
> the first time you dictate.

Then have them hold **right Option**, say a sentence, and release.

## Update

```bash
withy update
```

That pulls the latest source into the checkout the installer recorded, re-runs
the installer, reloads the menu-bar front end in place, and ends with the same
checks as a fresh install — **read them**, exactly as you would at install time
(`diagnose`, then the polished test sentence). The menu has the same thing as
**Update Withy Voice…**, which opens a Terminal so the pull and the checks are
visible. By hand it is `cd <the clone> && git pull && ./install.sh`; an install
older than the `update` command has no recorded checkout and says so.

**A re-run of the installer changes nothing the user chose.** Settings,
vocabulary, custom instructions, API keys and history live in `~/.config/withy`
and `~/.local/share/withy`; the installer rewrites only install facts (the
launcher path, the source path). The polishing backend, the speech model, the
local model and the record key stay as they are — unless you pass the flag that
makes that choice (`--polish-command`, `--polish-backend`, `--model`,
`--with-llm`), which is how to change one deliberately. So do not add flags to
an update "to be safe": a flag is a change.

After an update the menu may look identical. That is expected — the Spoon is
replaced on disk and reloaded, not reinstalled — so verify the way you verified
the install:

```bash
~/.local/bin/withy diagnose
~/.local/bin/withy run --text "um so the the plan is to test this" --dry
```

## Uninstall

```bash
rm -rf ~/.local/share/withy ~/.config/withy \
       ~/.local/bin/withy ~/.hammerspoon/Spoons/Withy.spoon
```

Then remove the `hs.loadSpoon("Withy")` line from `~/.hammerspoon/init.lua`.
Optionally `brew uninstall whisper-cpp ffmpeg ollama` and delete the model at
`$(brew --prefix)/share/whisper-cpp/`.

---

## Choosing a polishing backend — help them pick

Polishing adds punctuation, paragraphs, quotes and applies spoken
self-corrections. Transcription is always local; **only polishing has a choice**,
and it is in the menu under **Polishing LLM**:

| Option | Speed | Leaves the machine | Needs |
|---|---|---|---|
| Off | instant | no | nothing |
| Local LLM model (`qwen2.5:3b`) | ~1–5 s | **no** | Ollama + a ~2 GB model |
| Local CLI | ~15 s | depends on the tool | an assistant already installed |
| Remote OpenAI API | ~2–3 s | **yes** | an API key |
| Remote Anthropic API | ~2–3 s | **yes** | an API key |

**Recommend the local LLM model by default.** It is the option that needs no key, no
vendor review and no network. Recommend a remote API only if they say latency or
quality matters more than locality — and say plainly that the transcript is sent
to that provider.

### Do they want a local LLM model at all?

Ask; do not assume. It costs a ~2 GB model download plus a background runner
that holds the model in GPU memory for five minutes after each use. Measured on
an M2 Pro: the runner **idle** costs nothing (0.0% CPU, 22 MB), but it is
resident during that five-minute window, so steady dictation means it is
near-permanently loaded.

Quality is the bigger consideration. On a real 75-word dictation, a 3B local
model returned one wall of text while a hosted model returned three paragraphs
and removed a stutter. A larger local model (7B and up) closes much of that gap
if the machine has the memory.

**Recommend it when** the machine must not send text anywhere and there is no
company assistant installed. **Skip it when** either of the other two backends
is available — a local CLI is usually better and costs nothing extra.

Install or remove it later from the menu: **Polishing LLM → Local LLM model**. Both open a Terminal so the download or
uninstall is visible rather than hidden behind a menu item.

Once installed, the menu lists every model that has been pulled, so
`ollama pull qwen2.5:7b` is all it takes to offer a better one.

### Helping them set up "Local CLI"

This is often the best option on a **work machine**, because the company may
already provide a licensed assistant — so nobody has to distribute an API key.

Withy needs the **non-interactive** form: a command that takes a prompt on
standard input and prints the answer on standard output. Find out what they have:

```bash
for c in claude llm ollama codex cursor-agent copilot gemini q chatgpt; do
  command -v "$c" >/dev/null && echo "found: $c"
done
```

Then work out the right invocation. Common shapes:

Common shapes, as a starting point only:

| Tool | Non-interactive form |
|---|---|
| Claude Code | `claude -p` |
| `llm` (Simon Willison's) | `llm` |
| Ollama, as a CLI | `ollama run <model>` |
| Most others | `<tool> -p` |

If you are not sure, **test it before saving**:

```bash
echo "Add punctuation, return only the text: hello there how are you" | <their command>
```

Withy can check this for you — this is the authoritative test, because it runs
the command exactly as Withy will:

```bash
withy set-command "claude -p"
withy test-command
```

It reports separately whether the command is missing, errored, or "worked" but
printed a banner around the answer. Run it; do not assume.

Done by hand, the command must print the corrected sentence and nothing else — no banner, no spinner, no
"thinking" preamble. If it prints extra chrome, look for a quiet/print flag.

**Do not assume a smaller model is faster.** It is tempting to pin a fast-model
flag, and it can backfire: measured on Claude Code with the same audio,
`claude -p` took 4.5-7.5 s while `claude -p --model haiku` took 33.5-51.9 s.
Through a CLI, model choice interacts with process startup, caching and routing
in ways that are not predictable from the model's size.

So: try flags if you like, but **measure each one with `withy test-command`**,
which reports the elapsed time, and keep whichever is actually fastest on that
machine.

Set it from the menu (**Polishing → Set local CLI command…**) or:

```bash
withy set-command "claude -p --model haiku"
```

### API keys

Entered from the menu — the item says **API key needed** until one is stored,
then **API key available**. Clicking a hosted option with no key prompts for one.
Or:

```bash
withy set-key openai      # reads the key from stdin
withy set-key anthropic
withy keys                # which providers are configured
withy remove-key openai
```

Keys are stored mode 600 in `~/.config/withy/<provider>-key`, never in
`settings.json`.

---

# Part 2 — FAQ

Answer from here. These are the real questions people ask after installing.

### "I dictated something and it never appeared"

Nothing is ever lost — every dictation is written to history *before* Withy tries
to type it. Menu → **Recent dictations** → click one to copy it.

Common causes, in order:
1. **Focus moved** while it was transcribing, so the text went to another window.
2. **Nothing was said.** Withy detects silence and types nothing on purpose —
   see the next entry.
3. **Typing failed.** `/tmp/withy.log` will say so, and the text is in history.

```bash
withy history          # what was dictated
withy copy 0           # copy the most recent to the clipboard
withy retype 0         # type it again, wherever the cursor is now
```

### "I pressed the key again — did I lose the previous one?"

No. Releasing the key commits a take; pressing again starts a new one while the
previous is still transcribing and polishing. Both complete.

(Pressing again within a fraction of a second of releasing is treated as one
continuous take, on the assumption the release was accidental.) Once you release the key, the audio is
saved and the dictation is in history. If a take came out wrong:

```bash
withy retry 0          # re-run the whole pipeline from the saved audio
```

Menu → **Recent dictations** → **Redo from audio** does the same. Audio is kept
for `keep_audio_days` (default 7).

### "It typed 'Thank you.' and I didn't say anything"

That is a Whisper hallucination on silence, and Withy has a gate for it — if it
still happens, the gate let it through. Withy decides whether anyone spoke by the
**modulation spread** (the gap between loud and quiet frames), not by volume, so
it survives a noisy room. The threshold is deliberately generous, because typing
nothing when you spoke is worse than the reverse.

```bash
grep "modulation spread" /tmp/withy.log     # what it measured
withy settings speech_spread_db=15          # raise it if silence gets through
```

### "A word keeps coming out wrong"

Add it to the vocabulary — menu → **Edit vocabulary…**, or
`~/.config/withy/vocabulary.txt`. Space- or newline-separated, `#` for comments.

**Proper nouns only.** Never add ordinary English words, and keep the list to
tens of entries. This is measured, not stylistic: an auto-derived 3,000-term list
made the text *worse* 63% of the time it fired, because at that size almost any
spoken word collides with something.

The vocabulary also licenses the polishing model to repair a garbled attempt at
one of your terms — with `Homebrew` listed, a transcript saying "Homebro" is
corrected; without it, the correction is refused.

### "It didn't format my text / the punctuation is missing"

Withy discards the model's output whenever it fails a safety check, and types the
plain transcript instead. `/tmp/withy.log` gives the reason:

```
format: DISCARDED chunk (degenerate formatting: 0.96 commas per word)
format: reverted 1 substitution(s), kept formatting
```

The guarantee is that **no word you did not say can appear in the output**. A
substituted word is reverted; the formatting around it is kept.

### "It deleted my 'um' but kept 'no, scratch that'"

That is the rule, not a bug. Withy removes **disfluency** — filler words,
stutters, repeated words, and false starts where someone is visibly searching
for a phrase — because none of that was meant as content.

It does **not** delete text because you said "scratch that" or "I mean". Those
are deliberate speech, and deciding they were not meant is a judgement about
intent that belongs to the speaker. It is also the one edit the safety check
cannot catch: an invented word is refused and a substituted word reverted, but
deletions have to be allowed or filler removal would be impossible.

If someone wants retractions applied, that is one line in their own
instructions — menu → *Edit polishing instructions…*.

### "Can I change how it writes?"

Yes — menu → **Edit polishing instructions…** (`~/.config/withy/prompt.md`).
Plain instructions are enough; Withy appends the vocabulary and the transcript.
Include `{text}` to control the whole template.

Style is yours; the safety check is not affected by what you write there.

### "Can I use a different key? / fn doesn't work"

Menu → **Record key**: fn, right ⌥, right ⌘, right ⇧, right ⌃, left ⌥.

The default is **right Option, not fn**, because macOS binds fn to Apple
Dictation and most commercial dictation tools take it too. To use fn: turn off
the incumbent, set System Settings → Keyboard → *Press 🌐 to: Do Nothing*, then
pick it from the menu.

### "The first word or two gets cut off"

The microphone takes a few hundred milliseconds to open. Measure it:

```bash
withy diagnose --mic     # records ~2s and reports the gap
```

The audible chime is the cue — speak after it, not as you press.

### "Nothing happens at all when I press the key"

```bash
withy diagnose
```

Usually Hammerspoon is missing **Input Monitoring**. After granting it, menu →
**Reload**. If `diagnose` shows a binary as NOT RESOLVED, that is a PATH problem
in the launcher — re-run `./install.sh`.

### "How do I make sure nothing I say leaves this machine?"

**Offline mode** — ⌃⌥⌘O, or the menu. It blocks every polishing backend that
transmits and keeps a local model if one is installed, or turns polishing off if
not. The previous choice is restored when it is switched off.

Be precise with people about what counts: transcription is **always** local, so
only polishing can ever transmit. A remote API obviously does. **A local CLI
also does** — the command runs on their machine, but the assistant behind it
usually does not, and that distinction is easy to miss.

### "Does it work offline / is anything uploaded?"

Transcription is always local (`whisper.cpp`). Nothing is uploaded **unless** the
polishing backend is set to a hosted API — and that menu entry says "leaves this
Mac". On-device and local-CLI polishing keep everything on the machine (a local
CLI may itself call out; that depends on the tool).

### "Where is my data?"

| Path | What |
|---|---|
| `~/.local/share/withy/history.jsonl` | every dictation, plain text |
| `~/.local/share/withy/audio/` | recordings, kept `keep_audio_days` |
| `~/.config/withy/` | settings, vocabulary, instructions, API keys |
| `/tmp/withy.log` | the log |

```bash
withy purge 0     # delete all history and audio
withy purge 7     # keep the last week
```

Exclude those paths from backups if policy requires it.

### "The banner said 'taking longer than usual'"

A step overran, and the banner says so rather than leaving a spinner that looks
identical to a hang. The threshold is that backend's own median on this machine
once there is a history for it, and a default before that.

It is information, not an error — the dictation is still running and will still
be typed.

### "The menu says polishing took 40 seconds"

That hint appears at the top of the menu when the last dictation's polishing
went past 30 seconds, and it names the option responsible. Something is slow
enough to be worth changing: benchmark the alternatives (above) and switch.

Common causes: a local model too large for the machine, a CLI whose default
model does heavy reasoning on what is only a formatting task, or a slow network
on a remote API.

### "It's slow"

Transcription loads a 1.6 GB model, twice if the language is auto-detected.
Pinning the language skips a whole pass:

```bash
withy settings language=en
```

Polishing time depends entirely on the backend — see the table in Part 1.

### "How do I add or remove an API key?"

Menu → **Polishing LLM**. The entry reads *API key needed* until one is stored
and *API key available* afterwards, and clicking an option without a key prompts
for one. There are explicit *Enter…* and *Remove…* items too.

```bash
withy keys                # which providers are configured
withy set-key openai      # reads the key from stdin
withy remove-key openai
```

Keys live at `~/.config/withy/<provider>-key`, mode 600, never in
`settings.json`. Removing one warns if an exported environment variable would
still supply it.

### "How do I install or remove the local LLM model?"

Menu → **Polishing LLM → Local LLM model**. The entry states which piece is
missing — runner not installed, runner not running, or no model downloaded — and
offers the matching action. Both install and remove open a Terminal, because a
multi-gigabyte download or an uninstall should be visible rather than hidden
behind a menu item.

Removing lists exactly what it will delete and asks for confirmation first.

Nothing about this choice is permanent, and nothing else depends on it:
dictation works without it, and the other polishing options are unaffected.

### "Is my battery draining?"

Only if on-device polishing is installed and in use. Measured on an M2 Pro:

```
ollama daemon, no model loaded:   0.0% CPU, 22 MB
after a dictation:                ~2.4 GB pinned on the GPU, for 5 minutes
```

So the idle runner is free; the five-minute window after each dictation is not.
`ollama ps` shows whether a model is resident right now. Switching polishing to
a CLI or a hosted API, or removing on-device polishing from the menu, ends it.

### "Which speech model / polishing option should I use?"

Measure, do not guess:

```bash
withy benchmark          # both
withy benchmark speech   # speech models only
withy benchmark polish   # polishing options only
```

Or from the menu: **Speech model → Benchmark speech models…** and
**Polishing LLM → Benchmark polishing options…**.

Every model gets the **same input**, which is what makes the times comparable —
unlike the per-dictation timings elsewhere, where each dictation is different
speech of a different length. Results then appear beside each model in the menu.

The speech reference is one of the user's **own recordings**, kept aside the
first time a benchmark runs: their voice, microphone and room. The polishing
reference is a fixed transcript containing filler, a stutter, a retraction,
reported speech and an enumeration.

**It does not score quality, and says so.** It prints every transcript and every
polished result in full so a person can judge that part themselves. Faster is
not better: in one real run the faster backend also ignored an instruction to
drop filler that the slower one obeyed. Read the text, not just the times.

### "Can I try the same dictation with different settings?"

Yes, and this is the honest way to compare them. The audio is kept, so:
menu → **Recent dictations** → **Redo from audio**, after changing the speech
model, the polishing backend, or the instructions.

Same recording, one variable changed — which is the only way to tell whether a
setting actually helped rather than the dictation simply being easier. Tools
that discard the audio cannot do this.

### "Which models can I choose?"

```bash
withy models
```

Speech models are discovered on disk, so anything dropped into
`$(brew --prefix)/share/whisper-cpp/` as `ggml-<name>.bin` is offered, and the
menu can download eight common ones directly.

**The `-q5_0` variants are the same model quantised** — `large-v3-turbo-q5_0` is
547 MB against the plain turbo's 1549 MB, and correspondingly faster to load and
run, for a small accuracy cost. For dictation that is usually the right trade,
and it is the first thing to try if transcription feels slow. On-device
polishing offers whatever has been pulled — `ollama pull qwen2.5:7b` adds it to
the menu. Both are switchable from the menu (**Speech model**, and **Polishing →
Local LLM model**).
