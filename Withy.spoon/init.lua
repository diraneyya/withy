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

-- ── the mark ─────────────────────────────────────────────────────────────
-- A weeping willow, drawn in Inkscape and shipped as SVG alongside two
-- rasterisations of it.
--
-- It is loaded as a TEMPLATE image, which is what lets macOS recolour it for
-- light and dark menu bars and for a highlighted menu — an emoji cannot do
-- that, and a coloured PNG needs one asset per appearance.
--
-- Two treatments, because a menubar glyph is about 18 points tall and detail
-- does not survive that: "solid" is the artwork as drawn and reads as a dense
-- tree silhouette; "outline" trades weight for legibility and keeps the dome
-- and the hanging strands visible. Switchable from the menu.
local GLYPH = 22

-- Derived from this file's own path rather than hs.spoons.resourcePath(),
-- which only resolves while the Spoon is being loaded and returns nil
-- afterwards — so a lazily-rendered icon could not find its own artwork.
local SPOON_DIR = (debug.getinfo(1, "S").source:match("^@(.*/)")) or ""


-- ── indicator ────────────────────────────────────────────────────────────
-- A menubar glyph alone is not enough feedback: while dictating you are looking
-- at the text field, not the menu bar. So there is also a small on-screen
-- banner — deliberately at a screen EDGE and small, because a large centred one
-- ends up covering the very field being dictated into.
local BANNER = { w = 148, h = 30, margin = 10, radius = 8 }

-- One definition of each phase, used by both the menubar mark and the banner,
-- so the colour you see in the corner of the screen is the colour on the tree.
local PHASE = {
  recording    = { text = "Recording",    dot = { red = 0.95, green = 0.23, blue = 0.19, alpha = 1 } },
  transcribing = { text = "Transcribing", dot = { red = 1.00, green = 0.74, blue = 0.13, alpha = 1 } },
  formatting   = { text = "Polishing",    dot = { red = 0.25, green = 0.60, blue = 1.00, alpha = 1 } },
  typing       = { text = "Typing",       dot = { red = 0.30, green = 0.80, blue = 0.40, alpha = 1 } },
}

local imageCache = {}

local function markImage(phase, dark)
  local key = tostring(phase) .. ":" .. tostring(dark)
  if imageCache[key] then return imageCache[key] end

  local base = hs.image.imageFromPath(SPOON_DIR .. "willow.png")
  if not base then return nil end

  local spec = PHASE[phase]
  local ink = dark and { white = 1, alpha = 0.92 } or { white = 0, alpha = 0.85 }

  local c = hs.canvas.new({ x = 0, y = 0, w = GLYPH, h = GLYPH })
  -- hs.image:size() returns { w = , h = } — NOT width/height.
  local size = base:size()
  local w = size.w / size.h * GLYPH
  c:appendElements({ type = "image", image = base,
                     imageScaling = "scaleProportionally",
                     frame = { x = (GLYPH - w) / 2, y = 0, w = w, h = GLYPH } })

  if spec then
    c:appendElements({ type = "rectangle", action = "fill", fillColor = ink,
                       compositeRule = "sourceAtop" })
    c:appendElements({ type = "circle",
                       center = { x = GLYPH - 4.5, y = GLYPH - 4.5 },
                       radius = 4.0, action = "strokeAndFill",
                       fillColor = spec.dot, strokeWidth = 0.8,
                       strokeColor = dark and { white = 0, alpha = 0.6 }
                                          or { white = 1, alpha = 0.85 } })
  end

  local img = c:imageFromCanvas()
  c:delete()
  img:template(spec == nil)   -- template only when there is no colour to keep
  imageCache[key] = img
  return img
end

local function markFor(phase)
  return markImage(phase, hs.host.interfaceStyle() == "Dark")
end

-- Testing hook. The mark is built from several things that can each fail
-- silently — a missing file, a phase table out of scope, a template flag that
-- discards colour — and the only honest way to check it is to render what the
-- REAL function returns, not a copy of its logic in a scratch file.
function obj.debugMark(phase, dark)
  return markImage(phase, dark or false)
end

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
  if state == "recording" then
    self:_phase("recording")
  elseif state == "idle" then
    self:_phase(nil)
  end
end

-- One call sets both the mark and the banner, so they can never disagree.
function obj:_phase(phase)
  -- Defensive: the menubar icon is decoration, the hotkey is the product. An
  -- icon that fails to load must never stop dictation from working — it did
  -- exactly that once, because a throw here aborted start() before the event
  -- tap was ever created.
  if self.menu then
    local ok, img = pcall(markFor, phase)
    if ok and img then self.menu:setIcon(img) else self.menu:setTitle("~") end
  end
  self:_banner(phase)
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
    if st ~= "recording" and PHASE[st] then self:_phase(st) end
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
-- Anything slow or fallible — installing a runner, downloading gigabytes —
-- is handed to a visible Terminal rather than run silently behind a menu. The
-- command itself comes from the CLI so it is defined in exactly one place.
local function runVisibly(cmd)
  hs.osascript.applescript(
    'tell application "Terminal"\nactivate\ndo script '
    .. ("%q"):format(cmd) .. '\nend tell')
end

local function cliJSON(args)
  local out = hs.execute("'" .. cliPath() .. "' " .. args)
  local ok, decoded = pcall(hs.json.decode, out or "")
  return ok and decoded or nil
end

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
              -- Same feedback as a live dictation: reprocessing runs the whole
              -- pipeline and takes just as long, so it gets the same banner
              -- rather than appearing to do nothing.
              self.state = "working"
              self:_phase("transcribing")
              self:_followPhases()
              self:_run({ "retry", tostring(idx) }, function()
                self:_stopFollowing()
                self:_setState("idle")
              end)
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

  -- ── Polishing ──────────────────────────────────────────────────────────
  -- Four ways to run it, because the right answer depends on the machine:
  -- nothing leaves a laptop that must not talk to anyone; a work machine often
  -- already has a licensed assistant installed; a personal one may just want it
  -- fast. Key state is shown in the label so "why is this doing nothing" is
  -- answered before it is asked.
  local polishOn = setting("postprocess", true)
  local backend = setting("polish_backend", "local")

  local function hasKey(provider)
    return hs.fs.attributes(HOME .. "/.config/withy/" .. provider .. "-key") ~= nil
  end

  local function askKey(provider, label)
    local btn, key = hs.dialog.textPrompt(
      "Withy — " .. label .. " API key",
      "Paste your " .. label .. " API key.\n\nIt is stored in "
      .. "~/.config/withy/" .. provider .. "-key, readable only by you, and "
      .. "never written to settings.json.",
      "", "Save", "Cancel")
    if btn ~= "Save" or not key or #key < 10 then return false end
    -- Piped, not passed as an argument: a key on a command line is visible to
    -- anything that can read the process table.
    local f = io.popen("'" .. cliPath() .. "' set-key " .. provider, "w")
    if not f then return false end
    f:write(key); f:close()
    return true
  end

  local function remoteItem(provider, label, modelKey, modelDefault)
    local have = hasKey(provider)
    return {
      title = "Remote " .. label .. " API (" .. setting(modelKey, modelDefault) .. ") — "
              .. (have and "API key available" or "API key needed"),
      checked = polishOn and backend == provider,
      fn = function()
        if not hasKey(provider) and not askKey(provider, label) then return end
        saveSetting("postprocess", true)
        saveSetting("polish_backend", provider)
      end,
    }
  end

  -- On-device polishing is OPTIONAL. If the runner or a model is missing the
  -- entry offers to install it rather than appearing as a choice that silently
  -- does nothing.
  local inv = cliJSON("models --json") or {}
  local localInfo = inv.local_ or inv["local"] or {}

  local function onDeviceItem()
    local models = localInfo.installed or {}
    if not localInfo.usable then
      -- Name the actual cause, and offer the action that fixes THAT cause.
      -- "not running" wanting an "Install…" button is how a menu teaches people
      -- it is lying to them.
      local why, action
      if not localInfo.runner_installed then
        why, action = "not installed", "Install local model…"
      elseif not localInfo.runner_running then
        why, action = "runner not running", "Start the local model runner"
      else
        why, action = "no model downloaded", "Download a local model…"
      end
      return { title = "Local model — " .. why, menu = {
        { title = action,
          fn = function()
            local cmd = hs.execute("'" .. cliPath() .. "' install-cmd local")
            runVisibly((cmd or ""):gsub("%s+$", ""))
          end },
      } }
    end
    local sub = {}
    for _, m in ipairs(models) do
      sub[#sub + 1] = { title = m, checked = (m == localInfo.selected),
        fn = function()
          hs.execute("'" .. cliPath() .. "' set-model local " .. ("%q"):format(m))
          saveSetting("postprocess", true); saveSetting("polish_backend", "local")
        end }
    end
    sub[#sub + 1] = { title = "-" }
    sub[#sub + 1] = { title = "Remove local model…",
      fn = function()
        local cmd = hs.execute("'" .. cliPath() .. "' install-cmd remove-local")
        runVisibly((cmd or ""):gsub("%s+$", ""))
      end }
    return { title = "Local model (" .. tostring(localInfo.selected) .. ")",
             checked = polishOn and backend == "local", menu = sub }
  end

  local cliCmd = setting("polish_command", {})
  local cliLabel = (#cliCmd > 0) and table.concat(cliCmd, " ") or "not set"

  local function askCommand()
    local btn, cmd = hs.dialog.textPrompt(
      "Withy — local CLI",
      "Command that takes a prompt on standard input and prints the answer.\n\n"
      .. "At home this is usually:   claude -p --model haiku\n"
      .. "At work it may be:         aifx agent run claude -p\n\n"
      .. "Whatever assistant you have, use its non-interactive form.",
      (#cliCmd > 0) and cliLabel or "claude -p --model haiku", "Save", "Cancel")
    if btn ~= "Save" or not cmd or cmd == "" then return false end
    hs.execute("'" .. cliPath() .. "' set-command " .. ("%q"):format(cmd))

    -- Exercise it immediately. A wrong command fails silently and safely —
    -- polishing simply never happens — which is the right failure mode and a
    -- terrible experience, because nothing tells you why. (Observed live: a
    -- command saved as "claudee" left polishing quietly doing nothing.)
    hs.alert.show("Withy — checking that command…", 2)
    hs.task.new(cliPath(), function(code, out)
      local ok, res = pcall(hs.json.decode, out or "")
      local msg = (ok and res and res.message) or out or "No response."
      hs.dialog.blockAlert(
        (ok and res and res.ok) and "That command works" or "That command did not work",
        msg, "OK")
    end, { "test-command", "--json" }):start()
    return true
  end

  items[#items + 1] = { title = "Polishing LLM", menu = {
    { title = "Off — type exactly what was heard",
      checked = not polishOn,
      fn = function() saveSetting("postprocess", false) end },
    onDeviceItem(),
    { title = "Local CLI — " .. cliLabel,
      checked = polishOn and backend == "command",
      fn = function()
        if #setting("polish_command", {}) == 0 and not askCommand() then return end
        saveSetting("postprocess", true); saveSetting("polish_backend", "command")
      end },
    remoteItem("openai", "OpenAI", "openai_model", "gpt-4.1-mini"),
    remoteItem("anthropic", "Anthropic", "anthropic_model", "claude-haiku-4-5"),
    { title = "-" },
    { title = "Set local CLI command…", fn = askCommand },
    { title = "Enter OpenAI API key…",
      fn = function() askKey("openai", "OpenAI") end },
    { title = "Enter Anthropic API key…",
      fn = function() askKey("anthropic", "Anthropic") end },
    { title = "Remove OpenAI API key", disabled = not hasKey("openai"),
      fn = function() hs.execute("'" .. cliPath() .. "' remove-key openai") end },
    { title = "Remove Anthropic API key", disabled = not hasKey("anthropic"),
      fn = function() hs.execute("'" .. cliPath() .. "' remove-key anthropic") end },
    { title = "-" },
    { title = "Edit polishing instructions…",
      fn = function() hs.execute("'" .. cliPath() .. "' prompt edit") end },
  } }

  local speech = inv.speech or {}
  local speechMenu = {}
  for _, m in ipairs(speech.installed or {}) do
    speechMenu[#speechMenu + 1] = {
      title = m.name .. "  (" .. tostring(m.size_mb) .. " MB)",
      checked = (m.name == speech.selected),
      fn = function()
        hs.execute("'" .. cliPath() .. "' set-model speech " .. ("%q"):format(m.name))
      end }
  end
  speechMenu[#speechMenu + 1] = { title = "-" }
  -- ipairs, not pairs: the order these are offered in is meaningful
  for _, d in ipairs(speech.downloadable or {}) do
    local present = false
    for _, m in ipairs(speech.installed or {}) do
      if m.name == d.name then present = true end
    end
    if not present then
      speechMenu[#speechMenu + 1] = {
        title = "Download " .. d.name .. " (" .. d.size .. ") — " .. d.note,
        fn = function()
          local cmd = hs.execute("'" .. cliPath() .. "' install-cmd speech " .. ("%q"):format(d.name))
          runVisibly((cmd or ""):gsub("%s+$", ""))
        end }
    end
  end
  items[#items + 1] = { title = "Speech model", menu = speechMenu }

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
        self.state = "working"
        self:_phase("transcribing")
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
    self:_setState("idle")
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
