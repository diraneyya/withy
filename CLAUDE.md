# CLAUDE.md — orientation for a coding agent working from this repo

You have probably been pointed here with a request shaped like *"build us an
internal dictation tool so we can stop paying for Willow Voice."* This file tells
you what this repo is, what to read in what order, and where the traps are.

## What this repo is

A **blueprint**, not a product. It contains:

- `docs/` — the design, written from a system that has been in daily production
  use on macOS since May 2026.
- `reference/` — a working, de-personalised Python implementation of the
  transcribe + correct + inject pipeline.

The reference code runs. It is not packaged, signed, or fleet-ready — that is the
work being asked of you, and `docs/06-plugin-spec.md` specifies it.

## Read in this order

1. `README.md` — the pipeline diagram and the build-vs-buy framing.
2. `docs/01-pipeline.md` — the transcribe pipeline. **The flags are load-bearing.**
   Do not "clean up" `-mc 0`, the two-pass language detection, or the
   English-only vocabulary prompt. Each one is a fixed bug.
3. `docs/05-gotchas.md` — **read this before writing any code.** Roughly 60% of
   the effort in the original build went into discovering these, and almost every
   one of them fails silently.
4. `docs/06-plugin-spec.md` — what you are actually building.
5. The rest as needed.

## Decide the scope before you write anything

There are two different products here and conflating them wastes a week:

- **Scope A — dictation into the developer tool.** No system permissions, small,
  shippable in days. Does *not* replace a Willow licence, because people dictate
  into Slack and docs too.
- **Scope B — system-wide dictation.** Needs a background agent with
  Accessibility + Input Monitoring, code signing, notarisation, MDM. This is the
  one that replaces the licence.

**A Claude Code plugin cannot do Scope B.** Plugins run inside the CLI process;
they cannot own a global hotkey or type into Slack. If the request is "make it a
plugin" and the goal is "replace Willow", surface that gap early rather than
discovering it at demo time. The recommended sequence is A first, then B.

## Things not to re-derive

These were settled empirically. Changing them needs new evidence, not a
preference:

- **Two whisper passes, not one.** Detection is reliable; task selection is not.
  Single-pass auto-detect makes non-English speech come back translated,
  intermittently.
- **`-mc 0`.** Without it the decoder loops and repeats phrases dozens of times.
- **No LLM in the correction stage.** It was tried at two model sizes; both
  rewrote or over-deleted meaning. Filler removal and vocabulary swaps are
  deterministic problems.
- **Precision over recall in the matcher.** A recall-maximising phonetic matcher
  destroyed clean sentences. A false correction corrupts silently; a miss is
  visible and cheap.
- **Correction is English-only.** The matcher is English dictionary + metaphone.
- **History is written before injection, always.**
- **Mic selected by name, never index.**

## Things that genuinely are open

Real work, not settled:

- Real-word garble correction (`cube control → kubectl`, `easy two → EC2`) — needs
  a constrained model that *selects an ID from a code-generated candidate set* and
  never spells.
- Lowercase domain terms in the vocabulary index (`kubelet`) — needs a
  frequency + not-in-dictionary extraction pass.
- Accessibility-API text insertion instead of clipboard paste for long text.
- Non-macOS ports. The transcribe pipeline (`docs/01`, `03`) is portable Python;
  capture (`02`) and injection (`04`) are entirely macOS and need rewriting.
- Whether `base.en` is good enough for your fleet. Test with real voices.

## Ground rules

- **Do not put a network call in the transcribe path.** The entire value
  proposition is that audio does not leave the device. If you need TTS or an LLM
  later, build it as a separate feature with its own consent surface — and note
  that `edge-tts` is a cloud call despite feeling like a local library.
- **Do not commit generated vocabulary artifacts** (`vocab_index.json`,
  `vocab_prompt.txt`). They are a compact map of internal terminology.
- **Do not hardcode paths.** Everything resolves through
  `reference/dictation/config.py` and `DICTATION_*` environment variables. The
  original system had absolute paths in five files, which is why it worked on
  exactly one machine.
- **Log every stage.** The failure modes here are silent by nature — a zero-byte
  WAV, a disabled event tap, a truncated paste. Absence of an error means nothing.
- **Verify claims about local behaviour by running it**, not by reading. Several
  entries in `docs/05-gotchas.md` exist because something "obviously worked".

## Provenance

Extracted from a personal tool called `brain-voice`. Personal corpus data, paths,
and the notes-assistant half of that tool have been removed. Where this repo
describes something that was measured, it says what hardware and what model. Where
it is specifying something not yet built, it says so.
