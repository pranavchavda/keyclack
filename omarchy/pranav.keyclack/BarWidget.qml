import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Keyclack bar toggle.
//   left click  : mute / unmute (temporary)
//   right click : advance to the next sound pack (persists + hot-swaps live)
//   tooltip     : live state, current pack, click hints
//
// Polls `keyclack state`, which prints e.g.
//   running enabled pack=cherry-mx-red (pid N)
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

  readonly property bool on: status === "on"
  readonly property bool muted: status === "muted"
  readonly property bool off: status === "off"

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

  function click(button) {
    var cmd
    if (button === Qt.RightButton || button === Qt.MiddleButton) {
      cmd = root.exe + " next-pack"          // cycle pack (also persists)
    } else if (root.off || root.status === "unknown") {
      cmd = root.exe + " run"                 // start the daemon
    } else {
      cmd = root.exe + " toggle"              // mute / unmute
    }
    if (root.bar) root.bar.run(cmd)
    quickPoll.start()
  }

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

  readonly property string tooltip: {
    var packTxt = root.pack ? shortPack() : ""
    if (root.on)   return "Keyclack on" + (packTxt ? " · " + packTxt : "") + "\nleft: mute · right: next sound"
    if (root.muted)return "Keyclack muted" + (packTxt ? " · " + packTxt : "") + "\nleft: unmute · right: next sound"
    if (root.off)  return "Keyclack stopped\nclick to start"
    return "Keyclack…"
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf11c"  // FA solid "keyboard"
    // mute & stopped read as a dimmed key so state is obvious at a glance.
    opacity: root.on ? 1.0 : root.muted ? 0.55 : 0.4
    tooltipText: root.tooltip
    onPressed: function(b) {
      if (b === Qt.LeftButton || b === Qt.RightButton || b === Qt.MiddleButton)
        root.click(b)
    }
  }
}
