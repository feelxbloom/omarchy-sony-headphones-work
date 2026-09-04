import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Owns the conversation with the headphones. The helper's `watch` mode holds
// the Bluetooth link open and prints one JSON object per state change, so this
// is mostly a matter of keeping that process alive and folding its lines in.
Item {
  id: root

  property string helperPath: ""
  property string address: ""

  property var state: ({ connected: false })
  property string lastError: ""
  property bool starting: true

  readonly property bool connected: !!state.connected
  readonly property string mode: String(state.nc_mode || "off")
  readonly property int ambientLevel: state.ambient_level === null || state.ambient_level === undefined
    ? Model.MAX_AMBIENT_LEVEL : state.ambient_level
  readonly property bool focusOnVoice: !!state.focus_on_voice
  readonly property bool supportsWind: state.supports_wind !== false
  readonly property bool busy: setProcess.running

  signal changed()

  function argv(args) {
    var command = ["python3", helperPath]
    if (address !== "") command = command.concat(["--address", address])
    return command.concat(args)
  }

  // Paint the change immediately and let the device's own notification correct
  // us a moment later — the headphones always get the last word.
  function optimistic(patch) {
    var next = {}
    for (var key in state) next[key] = state[key]
    for (var patched in patch) next[patched] = patch[patched]
    state = next
    changed()
  }

  function set(key, value, patch) {
    if (!connected || helperPath === "") return
    if (patch) optimistic(patch)
    setProcess.command = argv(["set", key, String(value)])
    setProcess.running = true
  }

  function cycleMode() {
    var next = Model.nextMode(mode)
    set("nc", next, { nc_mode: next })
  }

  function setMode(next) {
    if (next !== mode) set("nc", next, { nc_mode: next })
  }

  function setAmbientLevel(level) {
    var clamped = Model.clampLevel(level)
    var patch = { ambient_level: clamped }
    // The helper switches to ambient sound when the level moves; mirror that
    // here so the panel does not flicker back to "noise cancelling" first.
    if (mode !== "ambient-sound" && mode !== "off") patch.nc_mode = "ambient-sound"
    set("ambient-level", clamped, patch)
  }

  function toggle(key, stateKey) {
    var patch = {}
    patch[stateKey] = !state[stateKey]
    set(key, patch[stateKey] ? "on" : "off", patch)
  }

  function choose(key, stateKey, value) {
    var patch = {}
    patch[stateKey] = value
    set(key, value, patch)
  }

  function refresh() {
    if (helperPath === "") return
    refreshProcess.command = argv(["--json", "status"])
    refreshProcess.running = true
  }

  function applyLine(line) {
    var text = String(line || "").trim()
    if (text === "" || text.charAt(0) !== "{") return
    try {
      state = JSON.parse(text)
      starting = false
      lastError = String(state.error || "")
      changed()
    } catch (e) {
      // A partial line is not worth surfacing; the next one will be whole.
    }
  }

  onHelperPathChanged: if (helperPath !== "") watchProcess.running = true

  Process {
    id: watchProcess
    running: false
    command: root.argv(["watch"])
    stdout: SplitParser { onRead: function(line) { root.applyLine(line) } }
    stderr: SplitParser { onRead: function(line) {
      var text = String(line || "").trim()
      if (text !== "") root.lastError = text
    } }
    onExited: {
      root.starting = false
      // The daemon exits when the helper cannot run at all, or when its own
      // socket goes away. Either way, come back rather than going quiet.
      restartTimer.restart()
    }
  }

  Process {
    id: setProcess
    running: false
    command: []
    stderr: SplitParser { onRead: function(line) {
      var text = String(line || "").trim()
      if (text !== "") root.lastError = text
    } }
    onExited: function(exitCode) {
      if (exitCode === 0) root.lastError = ""
      root.refresh()
    }
  }

  Process {
    id: refreshProcess
    running: false
    command: []
    stdout: SplitParser { onRead: function(line) { root.applyLine(line) } }
  }

  Timer {
    id: restartTimer
    interval: 5000
    repeat: false
    onTriggered: if (root.helperPath !== "") watchProcess.running = true
  }

  Component.onCompleted: if (helperPath !== "") watchProcess.running = true

  // Saving a file hot-reloads the plugin, which builds a new Service; without
  // this the old one's helper lingers, and a pile of them race to own the
  // Bluetooth link.
  Component.onDestruction: {
    restartTimer.stop()
    watchProcess.running = false
  }
}
