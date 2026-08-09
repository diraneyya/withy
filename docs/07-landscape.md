# 07 — Landscape, licences, and build-vs-buy

Written to be useful in a decision meeting, including the parts that argue against
building.

---

## The core observation

**The technology is free and open. Every product built on it is not.**

whisper.cpp is MIT. OpenAI's Whisper weights are MIT. ggml is MIT. The entire
transcription capability — the hard part, the part that took a research lab to
produce — costs nothing and can be redistributed freely.

Then look at what people actually install. Every packaged dictation tool on the
Mac, local ones included, gates on a licence. Free tiers exist and are **quota
limited** — superwhisper's free tier stops at a usage cap and asks for a licence
past it (verified in use, not read off a pricing page). VoiceInk is
source-available and paid. Whispering is genuinely free and open, and only writes
to the clipboard — it will not type into the focused field, which is the whole
ergonomic point. The one unlimited free option is Apple's built-in Dictation,
which has no custom vocabulary, no correction layer, and noticeably weaker
accuracy on technical speech.

So the situation is: the commodity is free, the packaging is a crowded paid
market, and **nobody is giving away an unlimited local dictation tool** — because
there is no business model in doing so.

That is precisely the gap an internal build fills. You are not competing with a
free product; you are assembling free components that no vendor has an incentive
to assemble for free. Your incentive is different from theirs: you are not selling
it, you are avoiding buying it.

---

## What else exists

Assessed mid-2026; pricing and capabilities move, so re-check before quoting any of
it.

| Tool | Model | Local? | Types into any app? | Unlimited free use? | Cost |
|---|---|---|---|---|---|
| **Willow Voice** | cloud | No | Yes | No | paid per seat |
| **Wispr Flow** | cloud | No | Yes | No | ~$12–15/user/mo; the funded leader |
| **superwhisper** | local (Parakeet default, Whisper swappable) | Yes | Yes | **No — free tier is quota-capped** | paid licence past the cap |
| **VoiceInk** | local | Yes | Yes | No | source-available, paid |
| **Whispering** | local | Yes | **No — clipboard only** | Yes | free / OSS |
| **macOS Dictation** | on-device | Yes | Yes | Yes | free, built in; no custom vocabulary |
| **This blueprint** | local | Yes | Yes | Yes | build cost only |

The last column is the one that changes the argument. There is no row that is
simultaneously local, types into any app, unlimited, and free — except the one you
build.

### What an internal build adds beyond "free"

Even against a hypothetical free competitor, these do not come from a vendor:

- **Vocabulary auto-derived from your own corpus.** Every commercial tool offers a
  manual dictionary the user maintains by hand, per user, forever. Deriving it from
  your service catalogue and runbooks is strictly better and is not something an
  outside vendor can do.
- **Fleet deployment with pre-granted permissions.** A PPPC profile keyed to your
  own signing identity turns a four-dialog first run into nothing.
- **Central configuration and a kill switch.**
- **A first-party answer to "what software holds Accessibility rights on our
  laptops".** A third-party dictation app with Accessibility and Input Monitoring
  is, in posture terms, a keylogger you have chosen to trust. Many organisations
  are far more comfortable with that when they built and signed it themselves —
  that argument tends to land harder in a security review than licence cost does.

---

## Licences in the dependency chain

| Component | Licence | Note |
|---|---|---|
| whisper.cpp | MIT | Clean |
| Whisper model weights (OpenAI) | MIT | Clean; mirror and checksum them |
| ggml | MIT | Clean |
| Hammerspoon | MIT | Clean licence — but see below |
| jellyfish (metaphone) | MIT/BSD | Verify the current version |
| **ffmpeg** | **LGPL or GPL depending on build** | **The one to check.** Homebrew's build typically enables GPL components |
| Silero VAD (if you add VAD) | MIT | Clean |

**ffmpeg is the item to resolve before shipping.** Either build LGPL-only (trivial
for "record mono PCM"), or drop it and capture through AVFoundation directly,
which is the better engineering answer for a native agent anyway.

**Hammerspoon's licence is fine; its posture is the problem.** It is a
general-purpose automation runtime with full scripting access and Accessibility
rights. Excellent for prototyping — the reference Lua is right here — and a hard
conversation to have with a security team as a fleet dependency. Prototype with it,
ship without it.

---

## Model choice

| Model | Size | Trade-off |
|---|---|---|
| `base.en` | 148 MB | Fast, low memory, English only. Noticeably weaker on proper nouns and accented speech. |
| `small` / `small.en` | ~490 MB | Reasonable middle. |
| `medium` | ~1.5 GB | Rarely worth it over turbo. |
| **`large-v3-turbo`** | **1.6 GB** | **The default recommendation.** Near-large accuracy at roughly turbo speed; multilingual. What the reference system runs. |
| `large-v3` | ~3 GB | Marginally better, materially slower. |

**Test with your own people's voices before choosing.** Accent robustness is
precisely where the large models earn their size, and a fleet is not a room full of
people who sound like the person who benchmarked it. A model that is excellent for
the evaluator and mediocre for a third of the company is a failed rollout.

Non-Whisper local options worth a look if you are optimising for speed:
**Parakeet** (NVIDIA, what superwhisper defaults to on Apple Silicon) and
**whisper-large-v3-turbo via MLX** are both faster than whisper.cpp on M-series
hardware for some workloads. The pipeline in this repo is model-agnostic behind
`transcribe.py` — swapping the engine touches one file.

---

## When *not* to build this

Stated plainly, because a blueprint that only argues one way is not useful:

- **Small teams.** Below roughly 50–100 seats the licence spend is smaller than the
  build cost and much smaller than the ongoing support cost. Buy, or let people
  expense a personal licence.
- **If nobody owns it after launch.** An unmaintained tool holding Accessibility
  rights is worse than a vendor. Model updates, OS upgrades breaking event taps,
  and permission-prompt regressions all need an owner.
- **If your fleet is mostly Windows or Linux.** Everything in `docs/02` and
  `docs/04` is macOS-specific and would need rewriting. The transcribe pipeline
  (`docs/01`, `docs/03`) ports unchanged — it is plain Python and a CLI — but that
  is the easy half.
- **If the requirement is really "meeting transcription".** Different product:
  diarisation, long-form audio, summarisation, calendar integration. This pipeline
  handles the audio-to-text part well and none of the rest.

The strongest case for building is a large fleet where audio leaving the device is
the blocker, or where paying per seat for an assembly of MIT-licensed components is
hard to justify. If that is your situation, the technical risk is low — the design
in this repo has been running daily for months — and the remaining work is
packaging and permissions, not machine learning.
