# CLAUDE.md — orientation for a coding agent

This is **Whisperbar**: local push-to-talk dictation for macOS. Hold a key,
speak, release, and the text is typed into the focused application. Everything
runs on the machine.

If you were asked to **install** it, stop reading this and follow `LLM.md`.
This file is for changing the code.

## Shape

```
whisperbar/          the pipeline (Python, stdlib only, runs on macOS's own python3)
  capture.py         ffmpeg -> 16 kHz mono WAV
  transcribe.py      whisper.cpp, two passes (detect language, then force it)
  correct.py         the deterministic rules that survived measurement
  format.py          the local LLM formatting pass + THE GATE
  inject.py          typing into the focused app
  history.py         append-only record; the recovery path
  pipeline.py        the whole flow in one function
  cli.py             command surface (the Spoon drives it; users never type it)
Whisperbar.spoon/    Hammerspoon front end: record key, menubar, watchdog
eval/run_eval.py     measures the formatting stage against real dictations
docs/                design rationale; 05-gotchas.md is the important one
```

The Python side never imports Hammerspoon and the Lua side never implements
pipeline logic. Keep it that way: it is what makes the pipeline testable with no
GUI, no microphone and no hotkey.

## Rules that are not style preferences

**1. Zero third-party Python dependencies.** It runs on `/usr/bin/python3`
(3.9). This is a large part of why installing is one command. Adding a `pip`
dependency is a design change, not a convenience — do not.

**2. Never widen the deterministic corrector.** Two rules were deleted after
measurement against 360 real dictations: phonetic out-of-vocabulary matching
(24 firings, **15 of them damaged the text**: badass→Bytes, gonna→Kuhn,
died→T8DE84EW) and hedge removal (20 firings, *every sampled one* legitimate).
The rationale is in `correct.py`'s docstring. If you want to reinstate
something, measure it first with `eval/run_eval.py` and show the numbers.

For a corrector, **precision beats recall**: a missed fix is visible and costs a
keystroke; a wrong fix is silent and ships.

**3. `format.gate()` is load-bearing — do not weaken it.** A small model given
an open brief rewrites meaning. The gate is what makes using one acceptable:
every output word must be a word spoken in that dictation, a vocabulary term, or
a list marker, else the output is discarded and the plain transcript is typed.
Read the exact guarantee in the docstring before changing it — it is a set
check, deliberately, and that is documented rather than overstated.

**4. Write history before injecting.** Always. Injection fails in ordinary ways
and the user must never lose words they spoke.

**5. Verify the effect, not the exit code.** Most failures here are silent: a
zero-byte WAV with exit code 0, a keystroke burst whose tail is dropped, an
`ollama` that answers but returns nothing. Check the artifact — the log, the
WAV's duration, the typed text — not the return code.

## Testing without a microphone

```bash
python3 -m whisperbar run --text "um so the the plan" --dry   # text stages only
python3 -m whisperbar run some.wav --dry                      # whole pipeline
python3 -m whisperbar diagnose                                # install health
python3 eval/run_eval.py --limit 50 --input history.jsonl     # formatting quality
```

`eval/run_eval.py` reads any JSONL with a `raw` field. The metric that matters
is the **gate rejection rate and its reasons** — a rate of zero on a small model
more likely means the gate is broken than that the model is perfect.

## Things that will bite you

All of them are in `docs/05-gotchas.md` with symptom → cause → fix. The four
that cost the most time:

- `-i ":0"` selects the first *enumerated* audio device, not the default. On a
  machine with an aggregate device it writes a **zero-byte WAV with exit code 0**.
  Always resolve by name (`capture.resolve_mic`).
- An `hs.eventtap` can be silently disabled by the system. The hotkey stops
  working with nothing in any log — hence the watchdog.
- Keystroke injection drops the tail of a long burst. Above
  `inject.KEYSTROKE_MAX` it must paste, not type.
- `kill -INT` the recorder, never `-KILL`: ffmpeg has to flush the WAV header.
