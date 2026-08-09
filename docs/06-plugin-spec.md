# 06 — Packaging this for a company

Everything before this file is proven, running code. **This file is a
specification.** It is written to be implemented and it flags where it is
speculating.

---

## First, split the scope

"Dictation" means two quite different products, with very different costs. Decide
which one you are building before writing anything.

### Scope A — dictation *into the developer tool*

Voice input for Claude Code / your IDE / your terminal. The audio never leaves the
machine, the text is inserted into a process you already control, and **no
system-wide permissions are needed**.

- Effort: small. The whole transcribe pipeline is in `reference/`.
- Delivery: a Claude Code plugin (MCP server + skill + command), or an IDE
  extension.
- Value: real but bounded. It does not replace a Willow licence, because people
  dictate into Slack, email, and docs, not just their editor.

### Scope B — system-wide dictation

Text into whatever app has focus. **This is what actually replaces the licence.**

- Effort: moderate. Needs a background agent with Accessibility and Input
  Monitoring, code signing, notarisation, MDM deployment, and a support story.
- Delivery: a signed menubar agent, pushed via MDM with a PPPC profile.
- Value: the whole thing.

**A Claude Code plugin cannot do Scope B on its own.** Plugins run inside the CLI's
process; they cannot own a global hotkey or inject keystrokes into Slack. Be
precise about this early — it is the assumption most likely to derail the plan.

The pragmatic sequence: **ship A first** (a week, no security review, immediate
users, and it proves the transcription quality on your people's actual voices),
then use its adoption to justify B.

---

## Scope A: a Claude Code plugin

A plugin is a directory with a `.claude-plugin/plugin.json` manifest, distributed
through a marketplace repo your company hosts. Consult the current plugin
documentation for exact schema — it moves — but the components you want are:

```
dictation-plugin/
├── .claude-plugin/
│   └── plugin.json
├── commands/
│   └── dictate.md          # /dictate — record, transcribe, insert
├── skills/
│   └── dictation/SKILL.md  # when and how the agent uses the tools
└── mcp/
    └── server.py           # tools: start_recording, stop_and_transcribe, transcribe_file
```

The MCP server is a thin wrapper over `reference/dictation/`:

| Tool | Does |
|---|---|
| `transcribe_file(path)` | Stage 1–3 on an existing audio file. The trivially useful one — voice memos, meeting recordings, a colleague's voice note. |
| `start_recording()` / `stop_and_transcribe()` | Push-to-talk without a hotkey: two tool calls bracketing the utterance. |
| `dictation_history(n)` | Recover a previous transcript. |

`transcribe_file` alone justifies the plugin. Handing an agent the ability to read
audio attachments is a genuinely new capability and costs you almost nothing once
the pipeline exists.

**Bundling the model** is the one real decision here. A 1.6 GB binary blob does not
belong in a plugin repo. Have the plugin check for the model at a configured path
and print install instructions if absent, and mirror the model internally.

---

## Scope B: the system agent

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Menubar agent (Swift, signed + notarised)              │
│                                                         │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  hotkey   │  │  AVFoundation│  │  text injection  │  │
│  │  (CGEvent │→ │   capture    │→ │  (AX API, then   │  │
│  │   tap)    │  │  16k mono    │  │   paste fallback)│  │
│  └───────────┘  └──────┬───────┘  └────────▲─────────┘  │
│                        │                   │            │
│                 ┌──────▼───────────────────┴─────────┐  │
│                 │  transcribe + correct              │  │
│                 │  whisper.cpp (libwhisper or CLI)   │  │
│                 │  + deterministic correction        │  │
│                 └────────────────────────────────────┘  │
│                                                         │
│  history JSONL · config from MDM-managed plist          │
└─────────────────────────────────────────────────────────┘
```

Link `libwhisper` directly rather than shelling out to `whisper-cli`. You keep the
model resident between utterances — which is most of the measured latency, since
the CLI reloads 1.6 GB on every one of the two passes — and you ship one binary
instead of managing a Homebrew dependency on 2,000 laptops. Expect roughly a 3×
improvement in perceived speed from this change alone.

Port the correction engine to Swift, or embed Python — but note that the whole
correction stage is about 400 lines of string manipulation plus a metaphone
implementation. Porting is a day's work and removes a Python runtime from your
deployment. Prefer porting.

### Configuration surface

Read from a managed preferences domain so MDM can set defaults and users can
override what you allow:

| Key | Default | Notes |
|---|---|---|
| `model` | `large-v3-turbo` | Path or identifier; allow `base.en` for older hardware |
| `hotkey` | `fn` hold | Must be user-configurable; `fn` conflicts with some accessibility setups |
| `micDevice` | system default | By name, never index |
| `vocabularyIndex` | managed path | Refreshed by a separate job |
| `historyRetentionDays` | 7 | See below |
| `correctionEnabled` | true | Per-user off switch for the vocabulary swaps |

### Rollout

1. **Dogfood, ~20 people, 2 weeks.** Instrument nothing but crashes and the local
   history count. Collect vocabulary misses by asking, not by telemetry.
2. **Opt-in beta** behind an internal marketplace / self-service portal entry.
3. **Broad availability.** Do not force-install; a dictation tool nobody asked for
   that holds Accessibility rights is a bad first impression.

The metric that matters is **weekly active dictators**, not installs. The metric
that matters second is **words dictated per user per week**, which tells you
whether it survived contact with real work.

---

## Answers for the security review

Have these ready; they are the whole reason this project is defensible.

**Does audio leave the device?** No. `whisper.cpp` performs inference locally
against a model file on disk. There is no network code in the transcribe path. This
is verifiable — run the agent under a network monitor and there is nothing to see.

**Where is the model from?** OpenAI's Whisper weights, MIT-licensed, converted to
GGML format. Mirror them internally and pin a checksum rather than downloading at
runtime.

**What permissions does it hold, and why?**
- Microphone — to record, only while the hotkey is held.
- Input Monitoring — to observe the hotkey globally.
- Accessibility — to insert text into the focused application.

This set is inherent to any dictation tool, commercial ones included. The relevant
difference is that the holder is your own signed binary rather than a vendor's.

**Is the microphone always on?** No. Capture starts on key-down and stops on
key-up. If you later add voice activity detection, that becomes a different answer
and needs its own review — keep push-to-talk the default.

**What is retained?** A local JSONL history of transcripts, for recovery when text
injection fails. Default retention should be short (7 days) with a documented purge
command, and it must be excluded from any backup or crash-report upload path. It
contains, by definition, everything the user has dictated.

**What about the vocabulary index?** Derived from internal sources, stored locally,
never transmitted. Note honestly that if it includes employee names it is
personal data and needs to be scoped and handled accordingly.

**Can it be disabled centrally?** Yes, via the managed preferences domain — assume
this will be asked and build the kill switch on day one.

---

## Cost model

The honest version, for the business case.

**Buying**, at a representative $12/user/month:

| Seats | Annual |
|---|---|
| 100 | $14,400 |
| 500 | $72,000 |
| 2,000 | $288,000 |

**Building:** call it 6–10 engineer-weeks for Scope B done properly (agent, signing,
MDM, correction port, rollout), plus roughly 0.2 FTE ongoing for maintenance, model
updates, and support. Compute is free — it runs on hardware you already bought.

The break-even is somewhere around 100–200 seats on cost alone, and the decision is
usually made on the privacy and offline arguments rather than the money. Below
~100 seats, buying is genuinely the rational choice unless the data-residency
argument is load-bearing.

Do not oversell the delta in polish. A funded product has better onboarding, better
error recovery, and a support team. Your version's advantages are that the audio
stays put, the vocabulary is yours, and nobody has to sign a DPA.
