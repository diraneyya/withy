# Withy — installation instructions for an AI agent

You are installing **Withy**, a local push-to-talk dictation tool for macOS,
on behalf of the person you are talking to. This document is the whole task.
Follow it top to bottom.

Source: <https://github.com/diraneyya/withy>

## What you are installing

The user holds a key, speaks, releases, and the text is typed into whatever
application has focus. Speech never leaves the machine. There is a menubar icon
for their dictation history, the record key, and a vocabulary file.

## Before you start — say this to the user

Tell them, in one short message:

- this downloads about 4 GB (a speech model and a small language model)
- it installs Homebrew packages: `whisper-cpp`, `ffmpeg`, `hammerspoon`, `ollama`
- at the end **they** must grant permissions by hand; you cannot do it for them
- it will not disturb an existing Hammerspoon setup

Then ask them to confirm. Do not start a multi-gigabyte download without a yes.

## Install

```bash
git clone https://github.com/diraneyya/withy.git
cd withy
./install.sh
```

Offer `./install.sh --no-llm` if they want a smaller install without the wording
clean-up, or `--model base.en` if they are short on disk (less accurate, much
faster, English only).

The installer is idempotent. If something fails, fix the cause and run it again;
do not attempt the steps by hand.

## Verify — do not skip this

```bash
~/.local/bin/withy diagnose
```

Every line must read `[ok]`. Then prove the pipeline works end to end without
needing the microphone or the hotkey:

```bash
~/.local/bin/withy run --text "um so the the plan is to test this" --dry
```

That should print a cleaned, punctuated sentence. If it prints the input
unchanged, the language model is not reachable — check `ollama list` and that
`ollama serve` is running. **Report what the command actually printed.** Do not
tell the user it works because a command exited 0.

## The part you cannot do

Permissions require a human at the keyboard. Tell the user, in these words:

> Open **System Settings → Privacy & Security**, and under **Accessibility**
> and **Input Monitoring**, switch on **Hammerspoon**. The microphone will be
> requested the first time you dictate.

Then have them hold **right Option**, say a sentence, and release it.

## Choosing the record key

The default is right Option, not `fn`. `fn` is the better key to hold, but macOS
binds it to Apple Dictation, and Willow Voice and Wispr Flow use it too — so it
is usually taken. If the user wants `fn`, tell them to:

1. turn off the incumbent (System Settings → Keyboard → Dictation, or quit the
   other tool), and set **Press 🌐 to: Do Nothing**
2. pick `fn (globe)` from the menubar → **Record key**

Both tools can be installed at once on different keys — that is the intended way
to trial Withy against whatever they use now.

## The vocabulary file

`~/.config/withy/vocabulary.txt` — words the speech model would otherwise
get wrong: project names, product names, acronyms, colleagues' names. Space- or
newline-separated, `#` for comments.

If you have access to the user's work — a repository, their notes, a wiki — you
can offer to populate it. Two rules:

- **Proper nouns only.** Never add an ordinary English word. Every entry is a
  chance to correct a word and a chance to corrupt one.
- **Keep it short.** Tens of terms, not thousands. This was measured: a
  3,000-term auto-derived list made the text worse 63% of the time it fired.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Nothing happens on the record key | Hammerspoon lacks Input Monitoring | grant it, then menubar → Reload |
| Text appears in the wrong window | focus moved during transcription | menubar → Recent dictations → Copy |
| Dictation is empty, no error | wrong input device | `withy mics`, then set `mic` in settings |
| Wording clean-up never applies | Ollama not running | `ollama serve`, then re-run `diagnose` |
| A word is consistently misheard | not in the vocabulary | add it to `vocabulary.txt` |

Logs: `/tmp/withy.log`. Nothing is ever lost — every dictation is in the
menubar history even when typing fails.

## Uninstall

```bash
rm -rf ~/.local/share/withy ~/.config/withy \
       ~/.local/bin/withy ~/.hammerspoon/Spoons/Withy.spoon
```

Then remove the `hs.loadSpoon("Withy")` line from `~/.hammerspoon/init.lua`.
