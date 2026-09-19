import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Keyclack settings panel: live state, volume, sound-pack picker.
//
// Opened by left-clicking the bar icon, or headlessly via Quickshell IPC:
//   quickshell ipc -p /usr/share/omarchy/shell call pranav.keyclack toggle
//
// All actions shell out to the keyclack CLI, which writes config and signals
// the running daemon (SIGUSR1 mute, SIGUSR2 volume/pack) — the panel never
// talks to the daemon directly, so CLI and panel can never disagree.
Panel {
  id: root
  moduleName: "pranav.keyclack.panel"
  ipcTarget: ""
  manageIpc: false

  // Own IPC so we can expose diagnostics alongside the lifecycle calls.
  IpcHandler {
    target: "pranav.keyclack"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    // Live wiring state, for debugging "icon red but no panel" issues:
    //   quickshell ipc -p /usr/share/omarchy/shell call pranav.keyclack diag
    // `dismiss` walks the same path as an outside-click dismissal
    // (KeyboardPanel.close -> owner.close), for testing reopen cycles.
    function dismiss(): void { panel.close() }
    function diag(): string {
      return JSON.stringify({
        opened: root.opened,
        anchorSet: !!root.anchorItem,
        barSet: !!root.bar,
        hostSet: !!root.hostWidget,
        panelOpen: panel.open,
        panelVisible: panel.visible,
        panelScreenSet: !!panel.screen,
        anchorWinSet: !!panel.anchorWindow
      })
    }
  }

  property var anchorItem: null
  property var hostWidget: null

  property var packs: []   // [{id, caption, active}] from `keyclack packs --json`
  property int volumePct: 90
  property int livePct: 90

  readonly property color foreground: bar ? bar.barForeground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.45)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  // Same per-machine absolute path as the bar widget (no PATH lookup in
  // Quickshell's Process); hostWidget supplies it once injected.
  readonly property string exe: hostWidget && hostWidget.exe
      ? hostWidget.exe : "/home/pranav/.local/bin/keyclack"

  onHostWidgetChanged: {
    if (hostWidget) {
      volumePct = Math.round(hostWidget.volume * 100)
      livePct = volumePct
    }
  }

  onOpenedChanged: {
    if (opened) {
      reloadPacks()
      if (hostWidget && hostWidget.refresh) hostWidget.refresh()
    }
  }

  function reloadPacks() {
    if (!packsProc.running) packsProc.running = true
  }

  function run(cmd) {
    if (hostWidget) hostWidget.run(cmd)
  }

  readonly property string heroMeta: {
    var hw = hostWidget
    if (!hw) return ""
    if (hw.off || hw.status === "unknown") return "Stopped"
    var packTxt = hw.pack ? hw.shortPack() : ""
    return (hw.muted ? "Muted" : "On") + (packTxt ? " · " + packTxt : "")
        + " · " + root.volumePct + "%"
  }

  // Pack clicks and CLI signalling are asynchronous; give config a beat to
  // settle before re-reading the pack list.
  Timer {
    id: packsSoon
    interval: 350
    onTriggered: root.reloadPacks()
  }

  Process {
    id: packsProc
    command: [root.exe, "packs", "--json"]
    stdout: StdioCollector { id: packsOut; waitForEnd: true }
    onExited: {
      try {
        root.packs = JSON.parse(String(packsOut.text || "").trim())
      } catch (e) {
        root.packs = []
      }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    contentWidth: panel.fittedContentWidth(Style.space(330))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(520))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      ScrollView {
        id: scrollArea
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: panelColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

        Column {
          id: panelColumn
          width: scrollArea.availableWidth
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: "Keyclack"
            meta: root.heroMeta
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconComponent: Component {
              Text {
                text: "\uf11c"  // FA solid "keyboard"
                color: root.foreground
                font.pixelSize: Style.font.display
                font.family: root.fontFamily
              }
            }
          }

          Row {
            width: parent.width
            spacing: Style.space(6)

            Button {
              width: (parent.width - parent.spacing) / 2
              text: {
                var hw = root.hostWidget
                if (!hw) return "Mute"
                if (hw.off || hw.status === "unknown") return "Start"
                return hw.muted ? "Unmute" : "Mute"
              }
              iconText: {
                var hw = root.hostWidget
                if (hw && (hw.off || hw.status === "unknown")) return "\uf04b"   // play
                return hw && hw.muted ? "\uf028" : "\uf026"   // volume-up / volume-off
              }
              bordered: true
              leftAlign: true
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: {
                var hw = root.hostWidget
                if (!hw) return
                if (hw.off || hw.status === "unknown") root.run(root.exe + " run")
                else root.run(root.exe + " toggle")
              }
            }

            Button {
              width: (parent.width - parent.spacing) / 2
              text: "Next sound"
              iconText: "\uf051"  // step-forward
              bordered: true
              leftAlign: true
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: {
                root.run(root.exe + " next-pack")
                packsSoon.start()
              }
            }
          }

          PanelSeparator { foreground: root.foreground }

          PanelSectionHeader {
            text: "VOLUME"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Row {
            width: parent.width
            Text {
              width: parent.width - volText.implicitWidth
              anchors.verticalCenter: parent.verticalCenter
              text: "Keyboard sounds"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.body
              font.bold: true
            }
            Text {
              id: volText
              anchors.verticalCenter: parent.verticalCenter
              text: root.livePct + "%"
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
            }
          }

          PanelSlider {
            width: parent.width
            bar: root.bar
            minimum: 0
            maximum: 100
            step: 1
            integer: true
            value: root.volumePct
            onMoved: function(v) { root.livePct = Math.round(v) }
            onReleased: function(v) {
              root.livePct = Math.round(v)
              root.volumePct = Math.round(v)
              root.run(root.exe + " set volume=" + (Math.round(v) / 100))
            }
          }

          PanelSeparator { foreground: root.foreground }

          PanelSectionHeader {
            text: "SOUND PACK"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Repeater {
            model: root.packs

            Button {
              required property var modelData
              width: parent.width
              leftAlign: true
              text: modelData.caption || modelData.id
              iconText: modelData.active ? "\uf00c" : ""   // check
              selected: modelData.active
              bordered: true
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: {
                root.run(root.exe + " pack " + modelData.id)
                packsSoon.start()
              }
            }
          }
        }
      }
    }
  }
}
