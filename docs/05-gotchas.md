# 05 — Every failure mode, and what actually caused it

Read this before writing code. Each entry cost real debugging time in a working
system. They are ordered roughly by how much time they cost.

The common thread: **almost every one of these fails silently.** No exception, no
non-zero exit, no log line. That is the defining characteristic of this problem
space — audio capture, ML inference, and synthetic input events all have a "looks
like it worked" failure mode. Instrument accordingly.

---

## Capture

### Zero-byte WAV, exit code 0

**Symptom:** dictation does nothing. No error anywhere.
**Cause:** `ffmpeg -i ":0"` selected a multi-channel aggregate device (BlackHole,
Loopback, Loom, Krisp) instead of the real mic. ffmpeg will not auto-downmix an
unknown high-channel layout and gives up quietly.
**Fix:** select the microphone by **name substring**, never by index. Make it
user-overridable. Check `-s "$WAV"` after recording and bail loudly if empty.

### Truncated or header-less WAV

**Cause:** the recorder was SIGKILLed, so ffmpeg never flushed the WAV header.
**Fix:** SIGINT, poll for exit up to ~2 s, then SIGKILL as a last resort.

### A 200 ms accidental tap produces a confident sentence

**Cause:** Whisper hallucinates on near-silence. It always produces *something*.
**Fix:** discard clips under 300 ms before transcription (`ffprobe -show_entries
format=duration`), and treat `(silence)` / `[BLANK_AUDIO]` / `.` output as empty.

---

## Hotkey layer

### The hotkey silently stops working

**Symptom:** works for hours, then nothing. No log entry. Restarting the host fixes
it.
**Cause:** macOS silently auto-disables event taps — after sleep, after a slow
callback, sometimes for no discoverable reason. The tap object still exists and
reports as valid; events just stop arriving.
**Fix:** a 1 Hz watchdog calling `:isEnabled()` and re-`:start()`ing. Plus a
30-second heartbeat in the log, so you can tell "tap died" from "watchdog died".

### The watchdog itself dies after ~30 minutes

**Cause:** Lua garbage collection. `hs.timer.doEvery` returns a userdata object
with no internal anchor; once the local reference goes out of scope at the end of
the init script, it is collected. Event taps survive because `:start()` registers
them internally — timers do not have that.
**Fix:** anchor every long-lived object in a global table (`_G.dictationRefs`).
**Generalise:** in any embedded scripting host, ask what keeps your background
objects alive. The answer is rarely "the runtime does".

### Recording state wedges "on" forever

**Cause:** a dropped key-up event, which macOS does when focus changes mid-press.
Your `isDown` boolean stays true and every subsequent press is a no-op.
**Fix:** the watchdog reconciles the boolean against the real modifier state each
tick — but must **skip reconciliation while a debounce stop is pending**, or it
races the debounce timer and double-stops the recording.

### One dictation becomes two

**Cause:** hand wobble, or macOS dropping and re-delivering a key event.
**Fix:** 200 ms release debounce; a re-press inside the window cancels the pending
stop.

---

## Transcription

### Non-English speech comes out translated into English

**Symptom:** you speak Arabic; English appears. Sometimes. Other times you get
correct Arabic script, other times a Latin transliteration of it.
**Cause:** Whisper is a multitask model trained on both *transcribe* and
*translate*. With no forced language, the task selection is effectively a lottery.
This is **not** a language-detection failure — detection measures p = 0.95–0.99 and
is reliable even on two-word clips.
**Fix:** detect first (`-dl`), then transcribe with `-l <lang>` forced.

### Forcing the language did not fully fix it

**Cause:** you are still passing an **English vocabulary `--prompt`** on
non-English audio. An English prior pushes the model back toward translating.
**Fix:** apply the bias prompt only when the detected language is English.

### A six-word phrase appears 56 times in a row

**Cause:** whisper.cpp conditions each 30-second decode window on previously decoded
text. A confidently-wrong token feeds itself forward and the decoder loops.
**Fix:** `-mc 0` disables cross-window text conditioning. On a 237 s test clip this
*reduced* output from 615 to 579 words with no content loss. Add
`collapse_phrase_repeats` downstream as a second line of defence — `-mc 0` reduces
the behaviour but does not eliminate it.

### Proper nouns are consistently wrong for one team but not another

**Cause:** the vocabulary bias list drifted from the corpus, or was built from a
corpus that does not contain that team's terms.
**Fix:** rebuild the index on a schedule and treat it as a data artifact with a
freshness SLA, not a file someone edits.

---

## Correction

### The corrector "fixed" words that were never wrong

`need → Node`, `note → Node`, `stacks → SDKs`. All exact metaphone collisions
(`NT`, `NT`, `STKS`).
**Cause:** a recall-maximising phonetic matcher over a few thousand corpus terms.
At that index size almost any short span shares an exact phonetic key with *some*
entry, and string similarity cannot separate the good match from the bad one.
**Fix:** gate on **out-of-vocabulary** and accept only exact matches. The
discriminator is not similarity — it is that "need" is a real word and "graphana"
is not. See `docs/03-correction.md`.

### Ordinary plurals get corrected into nonsense

`docs → DAGs`, `apps → APIs`, `reads → Redis`. In a corpus of infrastructure
documentation these are among the most common words in the language you speak all
day, which makes this failure loud.
**Cause:** `/usr/share/dict/words` holds base lemmas and is missing most plurals,
possessives, and verb inflections, so those tokens looked out-of-vocabulary.
**Fix:** de-inflect before the dictionary check — strip plural `-s/-es/-ies` and
verb `-ed/-ing` and re-check. Genuine garbles do not reduce to a dictionary word.

### The one word you most needed corrected is skipped

**Cause:** a naive contraction guard — "token contains an apostrophe, therefore
it's a contraction, skip". Whisper emits possessives, so the garble arrives as
`Kubernetti's`, not `kubernettis`.
**Fix:** drop apostrophes rather than splitting on them
(`Kubernetti's → kubernettis → KBRNTS → Kubernetes`), and skip only an explicit
list of genuine contractions.

### A local LLM in the correction stage rewrote meaning

**Cause:** using a small instruct model for a task with a closed answer set.
Open-ended correction hallucinated *answers*; deletion-span correction over-deleted
proper nouns and function words.
**Fix:** don't. Filler removal and vocabulary swaps are deterministic problems.
If you must involve a model, constrain it to **selecting an ID from a
code-generated candidate set** — never to producing text.

---

## Injection

### Nothing types, but copy/paste of the dictation works

**Symptom:** every dictation reaches history and the menubar copy actions work,
but nothing is ever typed into the focused app. The log shows
`inject(hs) FAILED rc=69: ... can't access Hammerspoon message port`.
**Cause:** `inject.py` prefers the Hammerspoon path whenever the `hs` binary
exists, injecting through `hs -c ...`. That command reaches Hammerspoon over its
ipc message port, which exists only once `hs.ipc` has been `require`d in the
running config. A freshly-installed Hammerspoon has **not** loaded it, so the
`hs` binary is present, the code takes the Hammerspoon path, and every call fails
before a single keystroke is posted. The `osascript` fallback never runs because
it is gated on the `hs` binary being *absent*, not on the call failing. It reads
as a permissions problem (recording works, typing does not) but Accessibility is
fine; the channel is simply not open.
**Fix:** load the module where Withy loads. Put `require("hs.ipc")` at the top of
the Spoon's `start()`, so the port is a guarantee of running Withy rather than
something the user must add to their own `init.lua`. Defence in depth: fall back
to the `osascript` path when the Hammerspoon call *fails*, not only when `hs` is
missing.

### Long dictations arrive truncated

**Symptom:** the first ~2,000 characters land, the rest vanishes. No error.
**Cause:** synthetic keystroke injection posts one event per character; the
receiving app drops the tail under a long burst.
**Fix:** above ~120 characters, paste via the clipboard instead (save → set → ⌘V →
restore). Also raise the subprocess timeout to 120 s — a 30 s cap can kill a
borderline-length keystroke run mid-type.

### Non-ASCII text breaks the approval/preview dialog

**Symptom:** any text containing an em-dash, an accent, or non-Latin script makes
the dialog return empty, instantly, with no error.
**Cause:** the command was rendered for display with `printf %q`, which under a C
locale mangles multibyte UTF-8 into invalid byte sequences. The AppleScript reading
it as UTF-8 then threw `-1700`, and the error was being discarded with `2>/dev/null`.
**Fix (three independent hardenings, all worth doing):**
1. never use `printf %q` for *display* — join plainly, and keep the real execution
   on the original argument array;
2. put the decode **inside** the error-handling block so failures are catchable;
3. never discard stderr from a helper you depend on.
**Bonus symptom:** a log file that has accumulated raw invalid bytes makes plain
`grep` treat it as binary and print nothing. Use `grep -a`, and don't conclude the
code never ran.

### The overlay covers the field being typed into

**Fix:** dismiss your own UI *before* injecting, not after.

### The user's clipboard was destroyed

**Cause:** restoring `nil` over a clipboard that held non-string data.
**Fix:** if you could not capture the previous contents, leave the dictation there
rather than clearing.

---

### The installer hangs forever with no output

**Symptom:** installation completes on disk — binaries in place, config written —
but the script never exits and prints nothing.
**Cause:** `hs -c 'hs.reload()'`. The reload tears down the very IPC channel the
`hs` client is blocked on reading, so the client waits for a reply that can never
come. Nothing is wrong; nothing will ever finish either.
**Fix:** detach it and do not wait: `( hs -c 'hs.reload()' >/dev/null 2>&1 & )`.
The same applies to any command that asks a process to restart itself through a
channel you are holding open.

### A menubar tool clobbers another one's configuration

**Cause:** Hammerspoon has a single `init.lua`, so two tools that each want to
*be* that file cannot coexist — and an installer that writes it destroys
whatever the user already ran.
**Fix:** ship as a **Spoon** and APPEND one `hs.loadSpoon(...)` line, after
backing the file up. Verify coexistence by checking the other tool's own log
after install, not by assuming.

## Deployment

### It works on the developer's machine and nowhere else

**Cause:** hardcoded absolute paths — the binary, the model, the corpus, the
Python. The original had `/Users/<name>/...` baked into five files.
**Fix:** environment variables with sensible defaults, resolved once in a config
module. The reference implementation uses a `DICTATION_*` prefix.

### First run is a wall of permission dialogs and half the fleet gives up

**Fix:** pre-grant Microphone, Accessibility, and Input Monitoring via a PPPC
configuration profile in MDM, keyed to your signing identity. This is the single
biggest adoption lever in the whole rollout.

### Model download is 1.6 GB per machine

**Fix:** mirror it internally and checksum it. Do not have 2,000 laptops pull from
Hugging Face on the same Monday morning. Consider whether `base.en` (148 MB) is
good enough for your users — test with their actual voices and accents before
deciding, because that is exactly where the large models earn their size.
