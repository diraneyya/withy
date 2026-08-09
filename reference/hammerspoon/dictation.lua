-- dictation.lua — push-to-talk hotkey layer for Hammerspoon.
--
-- Load from ~/.hammerspoon/init.lua with a single line, so editing this file
-- plus `hs -c "hs.reload()"` is the whole deploy cycle:
--
--     dofile("/path/to/reference/hammerspoon/dictation.lua")
--
-- Hold `fn` to record, release to transcribe and inject.
--
-- Hammerspoon is the right tool to PROTOTYPE this and the wrong dependency to
-- ship to a fleet — it is a general-purpose automation runtime holding
-- Accessibility rights. See docs/02-capture.md. Every behaviour below is what a
-- production Swift agent has to reimplement.

local REPO      = os.getenv("DICTATION_REPO") or (os.getenv("HOME") .. "/repos/local-dictation-blueprint")
local RECORD    = REPO .. "/reference/record.sh"
local PYTHON    = os.getenv("DICTATION_PYTHON") or "/usr/bin/python3"
local PKG_DIR   = REPO .. "/reference"
local WAV       = "/tmp/dictation-input.wav"
local STATE     = "/tmp/dictation-state"
local LOG       = "/tmp/dictation-hammerspoon.log"

local function flog(msg)
  local f = io.open(LOG, "a")
  if f then f:write(os.date("%H:%M:%S ") .. msg .. "\n"); f:close() end
end

-- ── GC anchor ───────────────────────────────────────────────────────────────
-- hs.timer.doEvery returns a userdata object with NO internal anchor: once the
-- local reference goes out of scope at the end of this file, Lua collects it.
-- Real bug — the watchdog died silently ~30 minutes after every reload, taking
-- exactly the recovery machinery below with it. Event taps survive because
-- :start() registers them in Hammerspoon's hook table; timers do not.
-- Anything outliving this script goes in here.
_G.dictationRefs = _G.dictationRefs or {}

-- ── earcons ─────────────────────────────────────────────────────────────────
-- Users cannot see an overlay while looking at their text field, and "did it
-- hear me?" is the most common anxiety. NEVER play a sound mid-recording — it
-- bleeds into the open mic and pollutes the transcript.
_G.dictationRefs.sndStart = hs.sound.getByName("Glass")
_G.dictationRefs.sndStop  = hs.sound.getByName("Bottle")
local function playStart() if _G.dictationRefs.sndStart then _G.dictationRefs.sndStart:play() end end
local function playStop()  if _G.dictationRefs.sndStop  then _G.dictationRefs.sndStop:play()  end end

-- ── overlay ─────────────────────────────────────────────────────────────────
local overlayId = nil
local function showOverlay(text)
  if overlayId then hs.alert.closeSpecific(overlayId) end
  overlayId = hs.alert.show(text, {
    textSize = 30, radius = 14,
    fillColor = { white = 0.05, alpha = 0.85 },
    strokeColor = { white = 1, alpha = 0.25 },
    textColor = { white = 1, alpha = 1 },
  }, hs.screen.mainScreen(), 86400)   -- "indefinite" is not a valid duration; use a big number
end
local function hideOverlay()
  if overlayId then hs.alert.closeSpecific(overlayId); overlayId = nil end
end

-- Poll the state file so the overlay reflects whatever stage owns the pipeline.
local poller, lastState = nil, nil
local function startPolling()
  if poller then return end
  lastState = nil
  poller = hs.timer.doEvery(0.25, function()
    local f = io.open(STATE, "r"); if not f then return end
    local s = (f:read("l") or ""):gsub("%s+$", ""); f:close()
    if s == lastState then return end
    lastState = s
    if s == "recording" then showOverlay("🎙  listening")
    elseif s == "transcribing" then showOverlay("🔄  transcribing…")
    else
      hideOverlay()
      if poller then poller:stop(); poller = nil end
    end
  end)
  _G.dictationRefs.poller = poller
end

-- ── the pipeline call ───────────────────────────────────────────────────────
local function runPipeline()
  hs.task.new("/bin/bash", nil, {
    "-lc",
    ("cd %q && %q -m dictation run %q"):format(PKG_DIR, PYTHON, WAV),
  }):start()
end

-- ── push-to-talk on fn ──────────────────────────────────────────────────────
-- `fn` (the globe key) is findable by feel, needs no chord, and macOS binds only
-- DOUBLE-tap fn (to system dictation) — press-and-hold is free.
--
-- Push-to-talk needs both down AND up, and hs.hotkey.bind only fires on down.
-- So: a raw eventtap on flagsChanged, filtered by keycode, reading the
-- post-event modifier state to tell press from release.
local FN_KEYCODE = 63
local fnDown = false
local fnPendingStop = nil

local ptt = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(ev)
  if ev:getKeyCode() ~= FN_KEYCODE then return false end
  local nowDown = ev:getFlags().fn == true

  if nowDown then
    if fnPendingStop then
      -- Re-press inside the debounce window: the user wobbled, or macOS dropped
      -- and re-delivered the event. Keep recording.
      fnPendingStop:stop(); fnPendingStop = nil
      flog("fn re-press within debounce — continuing")
    elseif not fnDown then
      fnDown = true
      playStart()
      flog("fn DOWN")
      startPolling()
      hs.task.new("/bin/bash", nil, { "-lc", ("%q start"):format(RECORD) }):start()
    end
  else
    if fnDown and not fnPendingStop then
      -- 200 ms release debounce. Without it, one long dictation becomes two
      -- truncated ones several times a day.
      fnPendingStop = hs.timer.doAfter(0.2, function()
        fnPendingStop = nil
        fnDown = false
        playStop()
        flog("fn UP — confirmed")
        hs.task.new("/bin/bash", nil, {
          "-lc", ("%q stop >/dev/null && true"):format(RECORD),
        }, function(code)
          if code == 0 then runPipeline() end
        end):start()
      end)
    end
  end
  return false   -- never swallow: other apps still need to see fn
end)
ptt:start()
_G.dictationRefs.ptt = ptt
flog("ptt started, isEnabled=" .. tostring(ptt:isEnabled()))

-- ── watchdog ────────────────────────────────────────────────────────────────
-- Two problems, both of which present as "the hotkey just stopped working":
--
-- 1. macOS SILENTLY auto-disables event taps — after sleep, after a slow
--    callback, sometimes for no discoverable reason. The object still exists and
--    reports as valid; events simply stop arriving. Nothing is logged.
-- 2. A dropped key-up (common when focus changes mid-press) leaves fnDown stuck
--    true, making every subsequent press a no-op.
--
-- The heartbeat matters: it is how you tell "the tap died" from "the watchdog
-- died" by reading the log alone.
local ticks = 0
_G.dictationRefs.watchdog = hs.timer.doEvery(1.0, function()
  ticks = ticks + 1
  if not ptt:isEnabled() then
    flog("watchdog: eventtap was disabled — restarting")
    ptt:start()
  end
  -- Skip reconciliation while a debounce stop is pending, or this races the
  -- timer and double-stops the recording.
  if fnDown and not fnPendingStop then
    if not hs.eventtap.checkKeyboardModifiers().fn then
      flog("watchdog: stuck fnDown detected — forcing stop")
      fnDown = false
      hs.task.new("/bin/bash", nil, { "-lc", ("%q cancel"):format(RECORD) }):start()
      hideOverlay()
    end
  end
  if ticks % 30 == 0 then flog("watchdog heartbeat") end
end)

flog("dictation.lua loaded")
