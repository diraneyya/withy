# Withy — instructions for an AI assistant

You are helping someone install, configure, or use **Withy**: local push-to-talk
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

## Install

```bash
git clone https://github.com/diraneyya/withy.git
cd withy
./install.sh
```

Offer `./install.sh --no-llm` to skip Ollama (they can still use a hosted API or
a local CLI for polishing, or turn polishing off), or `--model base.en` if disk
is tight — much faster, noticeably less accurate, English only.

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
cd withy && git pull && ./install.sh
```

Settings, vocabulary, custom instructions, API keys and history all live in
`~/.config/withy` and `~/.local/share/withy` and are untouched by a reinstall.

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
and it is in the menu under **Polishing**:

| Option | Speed | Leaves the machine | Needs |
|---|---|---|---|
| Off | instant | no | nothing |
| On device (`qwen2.5:3b`) | ~1–5 s | **no** | Ollama + a ~2 GB model |
| Use local CLI | ~15 s | depends on the tool | an assistant already installed |
| Hosted OpenAI | ~2–3 s | **yes** | an API key |
| Hosted Claude | ~2–3 s | **yes** | an API key |

**Recommend "on device" by default.** It is the option that needs no key, no
vendor review and no network. Recommend a hosted API only if they say latency or
quality matters more than locality — and say plainly that the transcript is sent
to that provider.

### Helping them set up "Use local CLI"

This is often the best option on a **work machine**, because the company may
already provide a licensed assistant — so nobody has to distribute an API key.

Withy needs the **non-interactive** form: a command that takes a prompt on
standard input and prints the answer on standard output. Find out what they have:

```bash
for c in claude aifx llm ollama codex cursor-agent copilot gemini q chatgpt; do
  command -v "$c" >/dev/null && echo "found: $c"
done
```

Then work out the right invocation. Common shapes:

| Tool | Command to enter |
|---|---|
| Claude Code | `claude -p --model haiku` |
| Claude via an internal wrapper | `aifx agent run claude -p` |
| `llm` (Simon Willison's) | `llm` |
| Ollama, as a CLI | `ollama run qwen2.5:3b` |
| GitHub Copilot CLI | `copilot -p` |
| Gemini CLI | `gemini -p` |

If you are not sure, **test it before saving**:

```bash
echo "Add punctuation, return only the text: hello there how are you" | <their command>
```

It must print the corrected sentence and nothing else — no banner, no spinner, no
"thinking" preamble. If it prints extra chrome, look for a quiet/print flag.

**Ask about the model.** The default model is usually a large reasoning one, and
polishing is a formatting task. Measured with Claude Code: the identical prompt
took **76.7 s** on the default model and **16.6 s** with `--model haiku`. If
their tool has a fast-model flag, use it — it is the difference between usable
and not.

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

### "I pressed the key again and lost my previous recording"

Pressing the record key **starts a new take and discards any recording still in
progress** — that is deliberate, it is how you cancel and re-speak without a
second key.

But a take that finished is not lost. Once you release the key, the audio is
saved and the dictation is in history. If a *finished* take came out wrong:

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

### "It's slow"

Transcription loads a 1.6 GB model, twice if the language is auto-detected.
Pinning the language skips a whole pass:

```bash
withy settings language=en
```

Polishing time depends entirely on the backend — see the table in Part 1.

### "Is my battery draining?"

Plausibly. Ollama pins the model in GPU memory for five minutes after each use
by default. Check with `ollama ps`. Switching polishing off, or to a hosted API,
removes that entirely.
