# 04 — Getting the text into the focused app

The unglamorous stage where dictation is actually won or lost. The transcript can
be perfect and the feature still feels broken if the text arrives truncated, into
the wrong window, or not at all.

Reference: `reference/dictation/inject.py`.

---

## Two paths, chosen by length

```python
KEYSTROKE_MAX = 120

if len(text) <= KEYSTROKE_MAX:
    synthetic_keystrokes(text)      # does not touch the clipboard
else:
    clipboard_paste(text)           # atomic, length-independent
```

### Short text → synthetic keystrokes

`hs.eventtap.keyStrokes` on macOS (or `CGEventKeyboardSetUnicodeString` if you are
writing this in Swift) posts one synthetic key event per character. Unicode-safe,
RTL-safe, and it leaves the user's clipboard completely alone — which matters,
because people keep things there.

### Long text → clipboard paste

Above the threshold, keystroke injection becomes **unreliable**: on a 3,267-character
dictation the receiving application dropped the tail. There is no error; the text
is simply short. The receiving app's event queue is the bottleneck and you cannot
see it from the sending side.

So: save the pasteboard, set it to the text, send ⌘V, and restore the old contents
0.5 s later.

```lua
local prev = hs.pasteboard.readString()
hs.pasteboard.setContents(t)
hs.eventtap.keyStroke({"cmd"}, "v")
hs.timer.doAfter(0.5, function()
  if prev then hs.pasteboard.setContents(prev) end
end)
```

Three details:

- **The restore must run in a persistent process.** If you shell out (`hs -c`) the
  command returns immediately; the timer only fires because it was scheduled inside
  the long-running Hammerspoon process. In a Swift agent this is just a
  `DispatchQueue.asyncAfter`.
- **If `prev` is nil, leave the dictation on the clipboard.** Nil means the
  clipboard was empty or held non-string data (an image, a file promise) that you
  could not capture. Clearing it would destroy something you never read. Leaving
  the dictated text there is harmless and occasionally useful.
- **This downgrades the privacy promise** from "never touches your clipboard" to
  "saves and restores it". Say so in your docs. Clipboard managers will record the
  dictation, and users with one installed should know.

A cleaner alternative exists on macOS: write the text directly into the focused
element via the **Accessibility API** (`AXUIElement`, setting `kAXValueAttribute`
or `kAXSelectedTextAttribute`). No clipboard, no keystroke queue, no length limit.
It works beautifully in native apps and inconsistently in Electron and web views —
which is where most dictation happens. Try it first, fall back to paste. Not
implemented in the reference code.

---

## Pass the text through a file, not a shell argument

If your injection host is invoked as a subprocess, do **not** interpolate the text
into a command line. You will spend an afternoon on quoting and still lose to an
apostrophe, an em-dash, or an Arabic string. Write it to a temp file and have the
host read it:

```python
TYPE_TMP.write_text(text, encoding="utf-8")
lua = f'local f=io.open([[{TYPE_TMP}]],"r");local t=f:read("a");f:close();hs.eventtap.keyStrokes(t)'
```

Related, and painful: **`printf %q` is for shell re-injection, not for display, and
it is locale-dependent on non-ASCII.** Under a C locale it mangles multibyte UTF-8
into invalid byte sequences — an em-dash (`E2 80 94`) becomes a lone raw `0xE2` plus
escapes. Anything downstream that decodes as UTF-8 then fails, often silently. If
you are rendering text for a dialog, join it plainly.

---

## Hide your own UI before injecting

Whatever overlay or HUD is showing "transcribing…" must be dismissed **before** the
text goes in. Two reasons: it may be covering the target field, and the user needs
to see focus visibly belonging to their text box at the moment text appears. This
is a one-line ordering fix that makes the feature feel considerably more solid.

---

## Never lose the text

Append to history **before** attempting injection, always, unconditionally. Then if
injection fails — and it will, because focus is not something you control — the
user runs:

```
dictation history list          # 1 = most recent
dictation history copy 1        # corrected text → clipboard
dictation history copy-raw 1    # pre-correction transcript instead
```

`copy-raw` matters more than it looks. When the correction stage swaps a word
wrongly, the user needs an escape hatch that is not "say the whole paragraph
again".

This single feature is the difference between "dictation is flaky" and "dictation
occasionally needs a paste". Users forgive the second.

---

## Timeouts

Give injection a generous subprocess timeout — 120 s, not 30. Keystroke injection
of a borderline-length string genuinely takes seconds, and a timeout that fires
mid-type leaves the user with half a sentence and no idea why. The paste path
returns instantly, so the generous ceiling costs nothing in the common case.

---

## Permissions (macOS)

Injecting keystrokes into other applications requires **Accessibility**
(`kTCCServiceAccessibility`). Observing a global hotkey requires **Input
Monitoring** (`kTCCServiceListenEvent`). Recording requires **Microphone**. All
three prompt on first use and all three can be pre-granted fleet-wide with a PPPC
configuration profile pushed by MDM — which is one of the strongest practical
arguments for an in-house build over a purchased app, because you control the
signing identity that the profile authorises.

Note that this permission set is, by design, "can see every keystroke and type
anywhere". Any dictation tool needs it — including the commercial ones. The
difference is whether the entity holding it is your own signed binary or a
third-party vendor's.
