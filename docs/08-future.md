# 08 — Future improvements

Ideas that have been thought through far enough to write down, but are not
built. Each says what it would give, what it costs, and what is still open.

---

## Tone: using HOW something was said, not only what

Whisper returns words and nothing else. Pitch, loudness and pauses are
discarded, so the polishing stage guesses punctuation from the words alone:
it cannot tell "you pushed it?" from "you pushed it." when the words are the
same. Tone has to be read from the audio itself. Three ways, in order of fit:

### 1. Prosody measured directly — no model

Pitch contour, loudness and pause length can be computed straight from the
waveform (e.g. a pitch tracker over the recorded WAV). Deterministic, cheap,
and fully local.

What it would give: evidence for the polishing stage instead of guesses.
A pitch rise at the end of a sentence → question mark; a long pause →
comma or paragraph break; a sharp pause → sentence end. Passed to the
polisher as hints aligned to the words, it would not weaken the guarantee
(the gate still reverts any word that was not said).

Open: aligning pitch and pauses to words needs word timestamps from whisper
(`-ml 1` / the JSON output), which the pipeline does not currently request.

### 2. A speech-emotion classifier — local model

Open models (e.g. emotion2vec) label a clip as angry / neutral / happy / sad
and run locally.

What it would give: a label on a passage, for a user who wants it
recorded (e.g. in history) or marked in the text.

Caveat: most are trained on acted emotional speech and are noticeably less
reliable on ordinary dictation. Measure on real history before trusting it.
Adds a model download.

### 3. An audio-native LLM — hosted

A model that listens to the recording rather than reading the transcript
hears tone and words together.

Caveat: the audio leaves the machine. The transcription stage has so far
never made a network call; this would need its own opt-in and its own
consent surface, like the hosted polishing backends.

### What is undecided

Whether tone is wanted for **punctuation** (option 1 fits, small and
well-defined) or for **marking emphasis or emotion** (options 2–3; a new
feature on a weaker footing — and the default polishing instructions forbid
markup, so emphasis would need a representation first).
