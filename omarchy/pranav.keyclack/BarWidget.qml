import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Keyclack bar entry + settings panel.
//   left click  : open/close the settings panel (volume, sound pack)
//   right click : mute / unmute (temporary)
//   middle click: next sound pack (persists + hot-swaps live)
//   tooltip     : live state, current pack, click hints
//
// Polls `keyclack state`, which prints e.g.
//   running enabled pack=cherry-mx-red volume=0.9 (pid N)
// Quickshell's Process does no PATH lookup on a bare argv[0], so the launcher
// is referenced by absolute path (same reason pranav.shopify hardcodes its
// script path). Glyphs are Font Awesome codepoints drawn by the shared bar
// font, which Qt falls back to the installed Nerd Font for.
BarWidget {
  id: root
  moduleName: "pranav.keyclack"

  readonly property string exe: "/home/pranav/.local/bin/keyclack"

  property string status: "unknown"   // on | muted | off | unknown
  property string pack: ""            // current pack id, e.g. cherry-mx-red
  property real volume: 0.9           // 0..1, mirrored from config via `state`

  readonly property bool on: status === "on"
  readonly property bool muted: status === "muted"
  readonly property bool off: status === "off"
  readonly property bool panelOpened: panelLoader.item
      ? panelLoader.item.opened === true : false

  visible: !root.vertical
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // "cherry-mx-brown" -> "brown", "subtle-clicks" -> "subtle", etc.
  function shortPack() {
    return String(root.pack || "").replace(/^cherry-mx-/, "").replace(/-/g, " ")
  }

  function refresh() {
    if (!stateProc.running) stateProc.running = true
  }

  function run(cmd) {
    if (root.bar) root.bar.run(cmd)
    quickPoll.start()
  }

  function click(button) {
    if (button === Qt.RightButton) {
      // quick mute/unmute without opening the panel
      if (root.off || root.status === "unknown") run(root.exe + " run")
      else run(root.exe + " toggle")
    } else if (button === Qt.MiddleButton) {
      run(root.exe + " next-pack")               // cycle pack (also persists)
    } else {
      // panel failed to load: fall back to mute so the click does something
      if (panelLoader.item) root.toggle()
      else if (root.off || root.status === "unknown") run(root.exe + " run")
      else run(root.exe + " toggle")
    }
  }

  // The panel's outside-click/Esc dismissal calls owner.close() — these
  // MUST exist on the host widget, otherwise KeyboardPanel falls back to
  // assigning its own `open` directly, which breaks the open: root.opened
  // binding forever after (icon toggles red, panel never maps again).
  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { if (panelLoader.item) panelLoader.item.toggle() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  onBarChanged: injectPanel()

  Timer { id: quickPoll; interval: 400; onTriggered: root.refresh() }

  Process {
    id: stateProc
    command: [root.exe, "state"]
    stdout: StdioCollector { id: stateOut; waitForEnd: true }
    onExited: function(exitCode) {
      var raw = String(stateOut.text || "").trim()
      var lower = raw.toLowerCase()
      if (lower.indexOf("running muted") === 0) root.status = "muted"
      else if (lower.indexOf("running") === 0) root.status = "on"
      else if (lower.indexOf("not-running") === 0) root.status = "off"
      else root.status = "unknown"
      var m = raw.match(/pack=([^\s)]+)/)
      root.pack = m ? m[1] : ""
      m = raw.match(/volume=([0-9.]+)/)
      if (m) root.volume = parseFloat(m[1])
    }
  }

  Timer {
    id: refreshTimer
    interval: 1200
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  readonly property string tooltip: {
    var packTxt = root.pack ? shortPack() : ""
    var stateTxt = root.on ? "Keyclack on" : root.muted ? "Keyclack muted"
        : root.off ? "Keyclack stopped" : "Keyclack…"
    return stateTxt + (packTxt ? " · " + packTxt : "")
        + "\nleft: settings · right: mute · middle: next sound"
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf11c"  // FA solid "keyboard"
    active: root.panelOpened
    // mute & stopped read as a dimmed key so state is obvious at a glance.
    opacity: root.on ? 1.0 : root.muted ? 0.55 : 0.4
    tooltipText: root.tooltip
    onPressed: function(b) {
      if (b === Qt.LeftButton || b === Qt.RightButton || b === Qt.MiddleButton)
        root.click(b)
    }
  }
}
