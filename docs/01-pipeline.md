# 01 — The transcribe pipeline

The complete path from a WAV file to corrected text. Five stages; stages 1–3 are
the transcribe pipeline proper, 4–5 are delivery.

Reference implementation: `reference/dictation/transcribe.py` and
`reference/dictation/cli.py`.

---

## Stage 0 — the input contract

The pipeline takes a **16 kHz, mono, 16-bit PCM WAV**. That is Whisper's native
input format; supplying anything else makes whisper.cpp resample internally, which
costs time and occasionally surprises you. Record it right the first time
(`docs/02-capture.md`).

Clips shorter than **300 ms** are discarded before transcription. They are almost
always an accidental key tap, and Whisper will happily hallucinate a sentence out
of 200 ms of room tone.

---

## Stage 1 — language detection (a separate pass)

```bash
whisper-cli -m <model> -dl <file.wav>
```

`-dl` runs detection only and prints, on stderr or stdout:

```
auto-detected language: en (p = 0.994)
```

Parsed with:

```python
re.search(r"auto-detected language:\s*(\w+)\s*\(p\s*=\s*([0-9.]+)\)", res.stderr + res.stdout)
```

Note it searches **both streams** — which one it lands on varies with whisper.cpp
version and flags. On a parse failure, fall back to `en` rather than erroring.

**Why a whole extra pass.** Whisper is a multitask model: it was trained on
*transcribe* and *translate*. Left to choose, it treats the task as a lottery on
non-English speech. The same Arabic phrase, spoken three times, came out as:

1. Arabic script (correct)
2. an English translation of itself
3. a Latin transliteration ("Show Asmoo")

This is not a language-identification failure. Detection is **rock solid**:
measured p = 0.994 for English, 0.955 for a two-word Arabic phrase, 0.998 for an
Arabic sentence. It is the *task* selection that is unstable. So: detect first,
then force.

The cost is roughly a second of extra latency, which is hidden behind the UI's
"transcribing…" state. A later optimisation could detect from the first 3 seconds
of audio only, or skip detection entirely for users who never code-switch.

---

## Stage 2 — transcription, with the language forced

```bash
whisper-cli -m <model> --no-prints -nt -mc 0 -l <lang> [--prompt "<vocab>"] <file.wav>
```

Every flag earns its place:

| Flag | Why |
|---|---|
| `-l <lang>` | The whole point of stage 1. Forcing the language eliminates the translate/transliterate lottery. |
| `-nt` | No timestamps. We want a plain paragraph, not an SRT. |
| `--no-prints` | Suppress whisper.cpp's banner so stdout is *only* the transcript. |
| `-mc 0` | **Max text context = 0.** See below — this is the single least obvious flag here. |
| `--prompt` | Vocabulary bias. English only. See below. |

### `-mc 0` — the repetition-loop guard

whisper.cpp conditions each 30-second decode window on the text decoded from
previous windows. When the model is confidently wrong about one token, that token
feeds itself forward and the decoder falls into a loop. Observed in production: a
six-word phrase emitted **56 times** in a row inside a four-minute dictation.

`-mc 0` disables cross-window text conditioning. On a 237-second test clip it
*reduced* total output from 615 to 579 words with no loss of content — the removed
words were all spurious repeats.

It composes fine with `--prompt`: the initial prompt is a separate mechanism from
decoded-text context, so you keep vocabulary bias while dropping the loop risk.

A second line of defence still exists downstream (`collapse_phrase_repeats` in
stage 3) because `-mc 0` reduces but does not eliminate the behaviour.

### `--prompt` — vocabulary bias, English only

whisper.cpp's `--prompt` text is **not transcribed**. It is fed as prior context so
the acoustic model is biased toward recognising those words. Give it your domain's
proper nouns and it stops hallucinating phonetically-similar mainstream words.

Format matters. Whisper biases best when the prompt reads like ordinary prose
rather than a wordlist dump:

```
Discussion topics include: Kubernetes, Datadog, Grafana, Terraform, PagerDuty, ...
```

Cap it around **120 terms / ~200 tokens**. The prompt eats context window, and
past a point additional terms dilute rather than help.

**Apply it only when the detected language is English.** An English bias prompt on
non-English audio pushes Whisper back toward translating. This was learned the
hard way; see `docs/05-gotchas.md`.

Generation of the term list is in `reference/dictation/correct/vocab.py` — walk
your corpus, extract proper-noun candidates by capitalisation and casing
heuristics, rank by frequency, take the top N.

### Output sanitisation

Whisper emits placeholder tokens for noise-only audio. Treat these as empty:

```python
if re.fullmatch(r"[\[\(].*[\]\)]|\.|\s*", text):
    return ""     # "(silence)", "[BLANK_AUDIO]", ".", ""
```

---

## Stage 3 — deterministic correction

Full treatment in `docs/03-correction.md`. In summary, three sub-stages, **no model
involved at any point**:

1. **Filler and stutter removal** — a closed list (`um`, `uh`, `erm`, …), immediate
   duplicate words, and a few multi-word hedges.
2. **Phrase-repeat collapse** — the second guard against whisper decode loops.
3. **Corpus proper-noun correction** — three narrow, high-precision rules that map
   garbled speech onto terms that actually exist in your corpus.

**Correction runs only for English.** The matcher is built on an English dictionary
and English metaphone keys; run it over Arabic or Japanese tokens and it will
cheerfully "correct" them into English proper nouns. Non-English transcripts pass
through untouched.

---

## Stage 4 — injection

Getting the text into the focused application. See `docs/04-injection.md`. The
short version: type it below a length threshold, paste it above one, and never lose
it either way.

---

## Stage 5 — history

Every utterance is appended to a JSONL file **before** injection is attempted:

```json
{"ts":"2026-08-09 14:22:01","raw":"…","final":"…","meta":{"lang":"en","removed":["um"],"swaps":[…]}}
```

This is not a nice-to-have. Injection fails in ordinary ways — the wrong window had
focus, the app swallowed the keystrokes, the user alt-tabbed mid-type. Without a
history the user has just lost a paragraph they spoke and cannot reproduce. With
one, recovery is `dictation history copy 1`.

Storing `raw` alongside `final` also gives you, for free, the corpus you need to
evaluate whether the correction stage is helping or hurting.

Retention is a policy decision for a corporate deployment — see
`docs/06-plugin-spec.md`.

---

## What was cut

The system this came from had a second half: the transcript could be handed to an
LLM that answered questions against a Markdown corpus and spoke the reply back
through TTS. That path **does** make network calls (to Anthropic, and to Microsoft's
edge-tts endpoint).

None of it is in this blueprint. Dictation and assistant are separable concerns,
and mixing them is what turns "a local transcription tool" into "a thing that needs
a security review". Keep them separate. If you later want a voice assistant, build
it as a distinct feature with its own consent surface, and note that
**`edge-tts` is a cloud call despite feeling like a local library** — an easy and
embarrassing mistake to make in a privacy pitch.

---

## Performance reference

Measured on an M2 Pro / 16 GB, `ggml-large-v3-turbo` (1.6 GB), whisper.cpp 1.8.4
with Metal:

| Operation | Time |
|---|---|
| Language detection pass (11 s clip) | 2.1 s |
| Transcription (11 s clip) | 1.7 s |
| **Full pipeline, cold, 11 s clip** | **~5.5 s** |
| Deterministic correction (any length) | < 5 ms |

Measured just now on the sample `jfk.wav` that ships with the Homebrew formula,
so it is reproducible: `whisper-cli -m ggml-large-v3-turbo.bin`.

**Model load dominates.** Each of the two passes reloads 1.6 GB from disk, and
that — not inference — is most of the 5.5 s. For push-to-talk this is tolerable
and keeps idle memory at zero, but it is the obvious thing to fix first:

- Run whisper.cpp as a **persistent server** (`whisper-server` ships with the
  same formula) and POST audio to localhost. Same model, same flags, no reload,
  at the cost of ~2 GB resident.
- Or **link `libwhisper` directly** in a long-running agent, which is what a
  production build should do anyway (see `docs/06-plugin-spec.md`).

Either turns a ~5.5 s round trip into roughly the 1–2 s of actual inference, and
lets you drop the separate detection pass to a fraction of a second by running it
against an already-loaded model.

One-time cost worth knowing about: the very first whisper.cpp invocation after
install compiles its Metal library (~9 s, logged as `ggml_metal_library_init`).
Warm it during install so no user ever sees it.

Smaller models are a real option for a fleet: `ggml-base.en` is 148 MB and much
faster, at a meaningful accuracy cost on proper nouns and accented speech. Test
with your own people's voices before choosing — accent robustness is where the
large models earn their size.
