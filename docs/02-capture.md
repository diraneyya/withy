# 02 — Audio capture and the hotkey layer

This is the most platform-specific part of the system and the part most likely to
need rewriting for your environment. The transcribe pipeline (`01`) is portable
Python; everything here is macOS.

---

## Recording

```bash
ffmpeg -hide_banner -loglevel error -nostdin \
       -f avfoundation -i ":MacBook Pro Microphone" \
       -ar 16000 -ac 1 \
       -y /tmp/take.wav
```

- `-f avfoundation -i ":NAME"` — the leading colon means *audio only, no video*.
  The name is matched as a **substring** of the device name.
- `-ar 16000 -ac 1` — Whisper's native format. Resample at capture, not later.
- Stop with **SIGINT**, not SIGKILL: ffmpeg needs to flush the WAV header. Send
  `kill -INT`, wait up to ~2 s in 100 ms polls, then `kill -KILL` as a backstop.

### Select the microphone by name, never by index

`-i ":0"` looks obvious and is a trap. Index 0 is *the first enumerated device*,
which is **not** the system default input. On any machine with BlackHole, Loopback,
Loom, Krisp, or an aggregate device installed — i.e. most developer laptops — index
0 is often a multi-channel aggregate reporting 16 or 17 channels. ffmpeg refuses to
auto-downmix an unknown high-channel layout and writes a **zero-byte WAV silently**,
exit code 0.

The symptom is "dictation does nothing" with no error anywhere. Match by name, and
make it overridable per user:

```bash
MIC="${DICTATION_MIC:-MacBook Pro Microphone}"
```

Enumerate devices with:

```bash
ffmpeg -f avfoundation -list_devices true -i ""
```

For a fleet deployment, resolving "the current system default input" properly is
worth doing — `SwitchAudioSource -c` (from `switchaudio-osx`) or a small
CoreAudio helper will give you the real default, which is what users expect when
they plug in headphones.

### ffmpeg licensing — check this before you ship

Homebrew's `ffmpeg` is typically built with GPL components enabled. Bundling a GPL
binary in an internally-distributed tool has implications your legal team will care
about, even for internal-only use. Options:

- Build ffmpeg LGPL-only (drop `--enable-gpl`); more than sufficient for
  "record mono PCM from a mic".
- Skip ffmpeg entirely and capture via **AVFoundation directly** in a ~100-line
  Swift helper. For a native macOS deployment this is the better answer anyway: no
  external binary, no process management, and you get level metering for the UI
  for free.
- Use `sox` (BSD-ish) — but it is less reliable on modern macOS audio devices.

whisper.cpp itself is MIT, and OpenAI's Whisper model weights are MIT. Those two
are clean. ffmpeg is the one to look at.

---

## Push-to-talk

The original uses [Hammerspoon](https://www.hammerspoon.org/) (MIT, Lua scripting
for macOS). Reference: `reference/hammerspoon/dictation.lua`. For a corporate
deployment Hammerspoon is probably the wrong dependency — see the end of this file
— but the *behaviours* below are what you need regardless of host.

### The key: use `fn`

`fn` (the globe key, bottom-left) is a good push-to-talk key on a Mac. It is
findable by feel without looking, needs no chord, and macOS only binds
*double-tap* fn (to system dictation) — a single press-and-hold does nothing, so
there is no conflict.

### Raw eventtaps, not hotkey bindings

Push-to-talk needs **both** key-down and key-up. Hammerspoon's `hs.hotkey.bind`
fires on down only. Use a raw eventtap on `flagsChanged`, filter by keycode
(fn = 63, right-option = 61), and read the post-event modifier state to tell press
from release:

```lua
local tap = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(ev)
  if ev:getKeyCode() ~= 63 then return false end
  local down = ev:getFlags().fn == true
  ...
  return false      -- never swallow: other apps still need to see fn
end)
```

### Debounce the release by 200 ms

Do not stop recording the instant the key lifts. Schedule the stop 200 ms out, and
cancel it if the key goes down again inside that window. This catches three real
situations:

- hand wobble — a finger briefly lifting and re-landing
- macOS dropping and re-delivering a key event
- the user re-gripping the keyboard mid-thought

Without it, one long dictation becomes two truncated ones several times a day.

### A watchdog is mandatory

**macOS silently disables event taps.** After sleep, after a callback runs slow, or
for no discoverable reason. The Lua object stays alive and reports as existing, but
no events arrive. The user's hotkey is simply dead, with nothing in any log.

Run a 1 Hz timer that:

1. calls `:isEnabled()` on each tap and `:start()`s it again if false;
2. reconciles your `keyDown` boolean against
   `hs.eventtap.checkKeyboardModifiers()` — if you missed a key-up (common when
   focus changes mid-press) the state heals within a second instead of wedging;
3. skips reconciliation while a debounce stop is pending, or it races the timer
   and double-stops;
4. logs a heartbeat every 30 s, so "hotkey is dead" can be distinguished from
   "watchdog is dead" from the log alone.

### Anchor long-lived objects against garbage collection

In Hammerspoon specifically: `hs.timer.doEvery` returns a userdata object that Lua
**will collect** once the local reference goes out of scope at the end of your init
file. Real bug: the watchdog died silently about 30 minutes after every reload,
disabling exactly the recovery machinery above.

Event taps survive because `:start()` registers them in Hammerspoon's internal hook
table. Timers have no such anchor. Keep a global table:

```lua
_G.dictationRefs = {}
_G.dictationRefs.watchdog = hs.timer.doEvery(1.0, ...)
```

Anything with a lifetime longer than the init script goes in it.

### Interrupt semantics

Pressing the record key while a previous utterance is still being processed should
**kill the in-flight work and start listening again**. It is the user's escape
hatch when a dictation is going wrong, and it means you need no separate cancel
key. Implement it as an unconditional sweep at the start of `record`:

```bash
pkill -f 'dictation/cli.py'   # in-flight transcription
kill -KILL "$(cat "$PID_FILE")" 2>/dev/null   # stale recorder
```

### Feedback the user needs

- **Earcons.** A short chime on record-start and a different one on record-stop.
  Users cannot see an overlay while looking at their text field, and "did it hear
  me?" is the most common anxiety. Note: never play a sound *during* recording —
  it bleeds into the open mic and pollutes the transcript.
- **A visible state overlay.** Drive it from a single state file
  (`recording | transcribing | injecting | idle`) written by whoever owns the
  current phase, polled at ~250 ms. One writer per phase, one source of truth.
- **Show the transcript before or as you inject it.** Split "transcribing" from
  "done" as two distinct states, and render the actual text on the transition.
  This gives the user a moment to see that a proper noun came out wrong and
  intervene, and it is the single largest trust-builder in the whole UI.

---

## Choosing a host for a corporate build

| Host | Pros | Cons |
|---|---|---|
| **Hammerspoon** | Fastest to prototype; everything above already written in Lua; MIT | A general-purpose scripting/automation runtime with full Accessibility rights — a hard sell to a security team, and a heavy dependency to push via MDM |
| **Small Swift menubar agent** | One signed, notarised binary; requests exactly the two permissions it needs; MDM-deployable via PPPC profile; no scripting runtime | You write the eventtap, watchdog, overlay, and injection yourself (all documented here) |
| **Existing internal agent** | If your fleet already runs a company daemon with Accessibility, add dictation to it | Couples release cycles |

For anything beyond a personal setup, **the Swift agent is the right answer**, and
this document is the specification for what it has to do. The permissions it needs
are Input Monitoring (to see the hotkey), Accessibility (to inject text), and
Microphone. Those can be pre-granted fleet-wide with a PPPC configuration profile,
which turns first-run from a four-dialog obstacle course into nothing at all.

---

## Voice activity detection instead of push-to-talk

Push-to-talk is deliberate: it is unambiguous, it never records by accident, and
"the mic is only live while I hold a key" is a sentence that ends a privacy
conversation quickly.

If you want hands-free, the local options are `whisper.cpp`'s built-in VAD
(`--vad` with a Silero model) or [openWakeWord](https://github.com/dscripka/openWakeWord)
for a wake word — both local, both free, both costing a few percent of a core at
idle. Keep push-to-talk as the fallback and the default; make hands-free opt-in.
An always-listening microphone is a materially different product to justify.
