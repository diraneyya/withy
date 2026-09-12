--- === Withy ===
---
--- Push-to-talk dictation. Hold a key, speak, release; the text is typed into
--- whatever has focus. Everything runs locally.
---
--- This Spoon is only the front end: a hotkey, a menubar, and a watchdog. All
--- of the work happens in the `withy` CLI, which it shells out to. That
--- split is deliberate — the pipeline stays testable without a GUI, and this
--- file stays small enough to audit.
---
--- Being a Spoon rather than an init.lua is what lets Withy coexist with
--- whatever else the user already runs under Hammerspoon.

local obj = {}
obj.__index = obj

obj.name = "Withy"
obj.version = "1.0.0"
obj.author = "Withy contributors"
obj.license = "Apache-2.0"
obj.homepage = "https://github.com/diraneyya/withy"

-- ── paths ────────────────────────────────────────────────────────────────
local HOME = os.getenv("HOME")
local SETTINGS = HOME .. "/.config/withy/settings.json"
local HISTORY = HOME .. "/.local/share/withy/history.jsonl"
local VOCAB = HOME .. "/.config/withy/vocabulary.txt"
local LOG = "/tmp/withy.log"

-- ── the record key ───────────────────────────────────────────────────────
-- A modifier is identified on a flagsChanged event by the KEYCODE of the key
-- that changed, which is the only way to tell left from right: getFlags() just
-- reports "alt", identically for both.
local KEYS = {
  { id = "fn",         code = 63, flag = "fn",    label = "fn (globe)" },
  { id = "rightalt",   code = 61, flag = "alt",   label = "right ⌥ option" },
  { id = "rightcmd",   code = 54, flag = "cmd",   label = "right ⌘ command" },
  { id = "rightshift", code = 60, flag = "shift", label = "right ⇧ shift" },
  { id = "rightctrl",  code = 62, flag = "ctrl",  label = "right ⌃ control" },
  { id = "leftalt",    code = 58, flag = "alt",   label = "left ⌥ option" },
}

local function keyById(id)
  for _, k in ipairs(KEYS) do if k.id == id then return k end end
  return KEYS[2]   -- right ⌥: fn is usually taken by an incumbent dictation tool
end

-- ── settings, shared with the Python side ────────────────────────────────
local function readSettings()
  local ok, s = pcall(hs.json.read, SETTINGS)
  if ok and s then return s end
  return {}
end

local function writeSettings(tbl)
  hs.fs.mkdir(HOME .. "/.config")
  hs.fs.mkdir(HOME .. "/.config/withy")
  hs.json.write(tbl, SETTINGS, true, true)
end

local function setting(key, default)
  local v = readSettings()[key]
  if v == nil then return default end
  return v
end

local function saveSetting(key, value)
  local s = readSettings()
  s[key] = value
  writeSettings(s)
end

-- ── the CLI ──────────────────────────────────────────────────────────────
-- The installer records where it put the launcher. The fallbacks exist so a
-- hand-placed install still works.
local function cliPath()
  local candidates = {
    setting("cli_path", nil),
    HOME .. "/.local/bin/withy",
    "/opt/homebrew/bin/withy",
    "/usr/local/bin/withy",
  }
  for _, p in ipairs(candidates) do
    if p and hs.fs.attributes(p) then return p end
  end
  return nil
end

function obj:_run(args, done)
  local bin = cliPath()
  if not bin then
    hs.notify.new({ title = "Withy", informativeText = "CLI not found — reinstall" }):send()
    if done then done(false) end
    return
  end
  hs.task.new(bin, function(code, _, err)
    if code ~= 0 and err and #err > 0 then print("withy: " .. err) end
    if done then done(code == 0) end
  end, args):start()
end

-- ── the frond ────────────────────────────────────────────────────────────
-- A withy is a willow branch cut for weaving, so the mark is a weeping willow
-- frond: a short bough with strands hanging from it.
--
-- It is drawn rather than shipped as a file, and set as a TEMPLATE image, which
-- is what lets macOS recolour it for light and dark menu bars and for a
-- highlighted menu. An emoji cannot do that, and a PNG would need two of them.
local GLYPH = 20     -- drawing box; the menubar renders it around 18pt

-- Each strand: where it leaves the bough, where it ends, and how far it bows.
local STRANDS = {
  { x = 4.5, y = 6.5, ey = 15.0, bow = -1.6 },
  { x = 8.0, y = 5.6, ey = 18.0, bow = -1.0 },
  { x = 12.0, y = 5.4, ey = 16.5, bow =  1.2 },
  { x = 15.5, y = 6.2, ey = 12.5, bow =  1.8 },
}

local function frondElements(color)
  local els = {
    -- the bough
    { type = "segments", action = "stroke", strokeWidth = 1.5,
      strokeColor = color, strokeCapStyle = "round",
      coordinates = { { x = 2.5, y = 7.5 },
                      { x = 17.5, y = 5.0, c1x = 7.0, c1y = 4.2, c2x = 13.0, c2y = 3.8 } } },
  }
  for _, st in ipairs(STRANDS) do
    els[#els + 1] = {
      type = "segments", action = "stroke", strokeWidth = 1.2,
      strokeColor = color, strokeCapStyle = "round",
      coordinates = { { x = st.x, y = st.y },
                      { x = st.x + st.bow * 0.5, y = st.ey,
                        c1x = st.x + st.bow, c1y = st.y + (st.ey - st.y) * 0.45,
                        c2x = st.x + st.bow * 0.9, c2y = st.y + (st.ey - st.y) * 0.8 } },
    }
  end
  return els
end

local iconCache = {}

local function frondIcon(state)
  if iconCache[state] then return iconCache[state] end
  local ink = { white = 0, alpha = 1 }          -- template images are recoloured
  local c = hs.canvas.new({ x = 0, y = 0, w = GLYPH, h = GLYPH })
  c:appendElements(table.unpack(frondElements(ink)))
  if state == "recording" then
    -- a bud on the frond, rather than a red dot floating beside it
    c:appendElements({ type = "circle", center = { x = 15.8, y = 16.0 }, radius = 2.6,
                       action = "fill", fillColor = ink })
  elseif state == "working" then
    c:appendElements({ type = "circle", center = { x = 15.8, y = 16.0 }, radius = 2.4,
                       action = "stroke", strokeWidth = 1.3, strokeColor = ink })
  end
  local img = c:imageFromCanvas()
  c:delete()
  img:template(true)
  iconCache[state] = img
  return img
end

-- ── indicator ────────────────────────────────────────────────────────────
-- A menubar glyph alone is not enough feedback: while dictating you are looking
-- at the text field, not the menu bar. So there is also a small on-screen
-- banner — deliberately at a screen EDGE and small, because a large centred one
-- ends up covering the very field being dictated into.
local BANNER = { w = 148, h = 30, margin = 10, radius = 8 }
local PHASE = {
  recording    = { text = "Recording",    dot = { red = 0.95, green = 0.25, blue = 0.25, alpha = 1 } },
  transcribing = { text = "Transcribing", dot = { red = 1.00, green = 0.72, blue = 0.20, alpha = 1 } },
  formatting   = { text = "Polishing",    dot = { red = 0.45, green = 0.70, blue = 1.00, alpha = 1 } },
  typing       = { text = "Typing",       dot = { red = 0.40, green = 0.85, blue = 0.45, alpha = 1 } },
}

function obj:_banner(phase)
  if not setting("banner", true) then return end
  local spec = PHASE[phase]
  if not spec then
    if self.canvas then self.canvas:hide() end
    return
  end
  -- Re-derive the frame each time so the banner follows the active screen.
  local scr = hs.screen.mainScreen():frame()
  local frame = { x = scr.x + scr.w - BANNER.w - BANNER.margin,
                  y = scr.y + BANNER.margin, w = BANNER.w, h = BANNER.h }
  if not self.canvas then
    self.canvas = hs.canvas.new(frame)
    self.canvas:level(hs.canvas.windowLevels.overlay)
    self.canvas:behavior(hs.canvas.windowBehaviors.canJoinAllSpaces)
    self.canvas:appendElements(
      { type = "rectangle", action = "fill",
        roundedRectRadii = { xRadius = BANNER.radius, yRadius = BANNER.radius },
        fillColor = { red = 0, green = 0, blue = 0, alpha = 0.74 } },
      { type = "circle", center = { x = 17, y = 15 }, radius = 5,
        action = "fill", fillColor = PHASE.recording.dot },
      { type = "text", frame = { x = 30, y = 6, w = BANNER.w - 36, h = 19 },
        text = "", textSize = 12.5,
        textColor = { white = 1, alpha = 0.95 } }
    )
  else
    self.canvas:frame(frame)
  end
  self.canvas[2].fillColor = spec.dot
  self.canvas[3].text = spec.text
  self.canvas:show()
end

function obj:_setState(state)
  self.state = state
  if self.menu then self.menu:setIcon(frondIcon(state or "idle")) end
  if state == "recording" then
    self:_banner("recording")
  elseif state == "idle" then
    self:_banner(nil)
  end
end

-- While the CLI is working it publishes its phase to a state file; follow it so
-- the banner says "Transcribing" and then "Polishing" rather than a generic
-- spinner. Nothing else in the Spoon knows about pipeline stages.
function obj:_followPhases()
  if self.poller then self.poller:stop() end
  self.poller = hs.timer.doEvery(0.2, function()
    local f = io.open("/tmp/withy-state", "r")
    if not f then return end
    local st = (f:read("l") or ""):gsub("%s+", "")
    f:close()
    -- Ignore "recording": the state file still holds it from the recorder that
    -- has only just been asked to stop, so honouring it here flips the banner
    -- back and forth between Recording and Transcribing on every key release.
    if st ~= "recording" and PHASE[st] then self:_banner(st) end
  end)
end

function obj:_stopFollowing()
  if self.poller then self.poller:stop(); self.poller = nil end
end

-- Any of /System/Library/Sounds. Glass is an unmistakable "the microphone is
-- open now" — a soft click is not, and a cue you have to squint at defeats the
-- purpose of an audible cue.
local SOUND_START = "Glass"
local SOUND_STOP  = "Bottle"

-- Held at module scope on purpose: hs.sound objects are garbage-collected like
-- timers are, and a sound collected mid-play simply goes silent.
local sounds = {}

local function chirp(name)
  if not setting("sound", true) then return end
  if sounds[name] == nil then sounds[name] = hs.sound.getByName(name) or false end
  local s = sounds[name]
  if s then s:stop(); s:play() end
end

-- ── history, read directly (a menu click should not wait on a process) ───
local function readHistory(limit)
  local out = {}
  local f = io.open(HISTORY, "r")
  if not f then return out end
  local lines = {}
  for line in f:lines() do if #line > 1 then lines[#lines + 1] = line end end
  f:close()
  for i = #lines, math.max(1, #lines - limit + 1), -1 do
    local ok, rec = pcall(hs.json.decode, lines[i])
    if ok and rec then out[#out + 1] = rec end
  end
  return out
end

local function ellipsis(s, n)
  s = (s or ""):gsub("%s+", " ")
  if #s <= n then return s end
  return s:sub(1, n - 1) .. "…"
end

-- ── menu ─────────────────────────────────────────────────────────────────
function obj:_buildMenu()
  local items = {}
  local key = keyById(setting("record_key", "rightalt"))

  items[#items + 1] = { title = "Hold " .. key.label .. " to dictate", disabled = true }
  items[#items + 1] = { title = "-" }

  -- History. Clicking an entry copies it; the submenu has the recovery paths.
  local hist = readHistory(10)
  if #hist == 0 then
    items[#items + 1] = { title = "No dictations yet", disabled = true }
  else
    local sub = {}
    for i, rec in ipairs(hist) do
      local idx = i - 1
      sub[#sub + 1] = {
        title = ellipsis(rec.final, 60),
        menu = {
          { title = rec.ts or "", disabled = true },
          { title = "Copy", fn = function() self:_run({ "copy", tostring(idx) }) end },
          { title = "Type again", fn = function() self:_run({ "retype", tostring(idx) }) end },
          { title = "-" },
          { title = "Copy unformatted", fn = function() self:_run({ "copy", tostring(idx), "--raw" }) end },
          { title = "Redo from audio", disabled = (rec.wav == nil),
            fn = function()
              self:_setState("working")
              self:_run({ "retry", tostring(idx) }, function() self:_setState("idle") end)
            end },
        },
        fn = function() self:_run({ "copy", tostring(idx) }) end,
      }
    end
    items[#items + 1] = { title = "Recent dictations", menu = sub }
    items[#items + 1] = { title = "Copy last", fn = function() self:_run({ "copy", "0" }) end }
  end

  items[#items + 1] = { title = "-" }

  -- Record key picker: the reason this exists is that fn is usually already
  -- owned by Apple Dictation or an incumbent tool.
  local keyMenu = {}
  for _, k in ipairs(KEYS) do
    keyMenu[#keyMenu + 1] = {
      title = k.label,
      checked = (k.id == key.id),
      fn = function() saveSetting("record_key", k.id); self:_rebind() end,
    }
  end
  items[#items + 1] = { title = "Record key", menu = keyMenu }

  items[#items + 1] = {
    title = "Clean up wording",
    checked = setting("postprocess", true),
    fn = function() saveSetting("postprocess", not setting("postprocess", true)) end,
  }
  items[#items + 1] = {
    title = "On-screen banner",
    checked = setting("banner", true),
    fn = function() saveSetting("banner", not setting("banner", true)) end,
  }
  items[#items + 1] = {
    title = "Sound", checked = setting("sound", true),
    fn = function() saveSetting("sound", not setting("sound", true)) end,
  }
  items[#items + 1] = {
    title = "Edit vocabulary…",
    fn = function() hs.execute("open -t '" .. VOCAB .. "'") end,
  }

  items[#items + 1] = { title = "-" }
  items[#items + 1] = { title = "Open log", fn = function() hs.execute("open -t " .. LOG) end }
  items[#items + 1] = {
    title = "Check setup…",
    fn = function()
      local bin = cliPath() or "withy"
      hs.execute("open -a Terminal " .. bin)   -- shows diagnose output in a window
      self:_run({ "diagnose" })
    end,
  }
  items[#items + 1] = { title = "Reload", fn = function() hs.reload() end }
  return items
end

-- ── push to talk ─────────────────────────────────────────────────────────
function obj:_rebind()
  if self.tap then self.tap:stop() end
  local key = keyById(setting("record_key", "rightalt"))
  self.down = false

  self.tap = hs.eventtap.new({ hs.eventtap.event.types.flagsChanged }, function(ev)
    if ev:getKeyCode() ~= key.code then return false end
    local isDown = ev:getFlags()[key.flag] == true

    if isDown then
      -- A re-press inside the release debounce means the user never actually
      -- let go; keep the take running rather than starting a second one.
      if self.pendingStop then
        self.pendingStop:stop(); self.pendingStop = nil
        return false
      end
      if not self.down then
        self.down = true
        self:_setState("recording")
        chirp(SOUND_START)
        -- Surface a failed start. Showing the recording indicator regardless of
        -- whether the recorder actually started is how this looked like it was
        -- working while capturing nothing at all.
        self:_run({ "start" }, function(ok)
          if not ok then
            self.down = false
            self:_setState("idle")
            hs.notify.new({ title = "Withy",
                            informativeText = "Could not start recording — see /tmp/withy.log" }):send()
          end
        end)
      end
    elseif self.down and not self.pendingStop then
      -- macOS emits spurious modifier flaps; a short debounce stops one hold
      -- from becoming two dictations.
      self.pendingStop = hs.timer.doAfter(0.2, function()
        self.pendingStop = nil
        self.down = false
        self:_setState("working")
        self:_banner("transcribing")
        self:_followPhases()
        chirp(SOUND_STOP)
        self:_run({ "stop" }, function(ok)
          self:_stopFollowing()
          self:_setState("idle")
          if not ok then
            hs.notify.new({ title = "Withy",
                            informativeText = "Nothing was transcribed — see /tmp/withy.log" }):send()
          end
        end)
      end)
    end
    return false   -- never swallow the event; other apps still see the key
  end)
  self.tap:start()
end

-- ── watchdog ─────────────────────────────────────────────────────────────
-- An eventtap can be silently disabled by the system (a permissions change, a
-- wedged event queue, waking from sleep) and the symptom is simply that the
-- hotkey stops working with nothing in any log. Re-arming it costs nothing.
function obj:_startWatchdog()
  self.watchdog = hs.timer.doEvery(30, function()
    if self.tap and not self.tap:isEnabled() then
      print("withy: event tap was disabled — restarting")
      self.tap:start()
    end
    -- Reconcile a stuck "held down" state: if the key is not actually held,
    -- the key-up was lost and the next press would be ignored forever.
    if self.down and not self.pendingStop then
      local key = keyById(setting("record_key", "rightalt"))
      if not hs.eventtap.checkKeyboardModifiers()[key.flag] then
        self.down = false
        self:_setState("working")
        self:_run({ "stop" }, function() self:_setState("idle") end)
      end
    end
  end)
end

-- ── lifecycle ────────────────────────────────────────────────────────────
function obj:start()
  self.menu = hs.menubar.new()
  if self.menu then
    self.menu:setIcon(frondIcon("idle"))
    self.menu:setMenu(function() return self:_buildMenu() end)
  end
  self:_rebind()
  self:_startWatchdog()
  return self
end

function obj:stop()
  if self.tap then self.tap:stop() end
  if self.watchdog then self.watchdog:stop() end
  if self.menu then self.menu:delete() end
  return self
end

return obj
