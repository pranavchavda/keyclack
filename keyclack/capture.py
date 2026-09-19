"""Keyboard device discovery and raw event capture via evdev.

Works on Wayland because we read /dev/input directly (no X11 grab needed).
Multiple processes / apps can read the same device: opening it for reading is
a passive copy and does not steal events from anything else.
"""

from __future__ import annotations

import select
import threading
from evdev import InputDevice, ecodes, list_devices

from .roles import key_name

# Minimal capability set that marks a device as a real typing keyboard.
_REQUIRED = {ecodes.KEY_A, ecodes.KEY_Z, ecodes.KEY_ENTER}

# Names/physics of synthetic keyboards (Logitech "solaar-keyboard", our own
# test device, etc.) that we must NOT treat as a real board for daily use.
def _is_synthetic(path: str, name: str, phys: str) -> bool:
    blob = f"{path} {name} {phys}".lower()
    return "uinput" in blob or "solaar" in blob or "virtual" in blob


def discover_keyboards(include_synthetic: bool = False):
    """Yield (path, name, phys) for devices that look like typing keyboards.

    Synthetic uinput keyboards are skipped unless ``include_synthetic`` is set.
    """
    found = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except (OSError, PermissionError):
            continue
        try:
            caps = dev.capabilities(verbose=False)
        except OSError:
            continue
        keys = set(caps.get(ecodes.EV_KEY, []))
        if not _REQUIRED.issubset(keys):
            continue
        if not include_synthetic and _is_synthetic(path, dev.name, dev.phys or ""):
            continue
        found.append((path, dev.name, dev.phys or ""))
    return found


class Capture:
    """Owns reader threads for a chosen set of keyboard devices.

    On every key *press* the configured handler is called with
    ``handler(code:int, value:int, name:str)`` where value is the evdev state
    (1 = press).  Returns nothing.

    Keyboards come and go after the daemon starts: Bluetooth boards connect
    late, sleep, and reconnect on a different node. Call ``rescan()``
    periodically to open devices that appeared and close ones that went away.
    """

    def __init__(self, handler, play_on_repeat: bool = False,
                 include_synthetic: bool = False):
        self.handler = handler
        self.play_on_repeat = play_on_repeat
        self.include_synthetic = include_synthetic
        self._live: dict[str, tuple[InputDevice, threading.Thread]] = {}
        self._stop = threading.Event()
        self.opened: list[str] = []

    # -- selection --------------------------------------------------------
    def _select(self, config_devices) -> list:
        kbds = discover_keyboards(include_synthetic=self.include_synthetic)
        if not kbds:
            return []
        if config_devices == "auto" or not config_devices:
            return kbds
        allowed = list(config_devices) if isinstance(config_devices, list) \
            else [config_devices]
        chosen = []
        for path, name, phys in kbds:
            haystack = f"{path} {name} {phys}".lower()
            if any(a.lower() in haystack for a in allowed):
                chosen.append((path, name, phys))
        return chosen

    def start(self, config_devices) -> int:
        """Open chosen devices and start a reader thread per device."""
        self._stop.clear()
        for path, name, phys in self._select(config_devices):
            self._open(path, name)
        return len(self._live)

    def _open(self, path: str, name: str) -> bool:
        """Open one device and spawn its reader thread."""
        try:
            dev = InputDevice(path)
        except (OSError, PermissionError) as exc:
            print(f"keyclack: cannot open {path} ({name}): {exc}")
            return False
        try:
            dev.grab()  # not needed for passive read, and would block others
        except Exception:
            pass
        dev.ungrab()
        t = threading.Thread(target=self._read_loop, args=(dev,),
                             name=f"kbd-{path}", daemon=True)
        self._live[path] = (dev, t)
        self.opened.append(f"{name}  [{path}]")
        t.start()
        return True

    def _close(self, path: str) -> None:
        """Drop one device. Its reader thread exits on its own: select()
        times out within 0.3s, then read() on the closed fd fails."""
        dev = self._live.pop(path)[0]
        line = f"{dev.name}  [{path}]"
        if line in self.opened:
            self.opened.remove(line)
        try:
            dev.close()
        except Exception:
            pass

    def rescan(self, config_devices) -> tuple[list[str], list[str]]:
        """Reconcile open devices with the keyboards plugged in right now.

        Opens devices that appeared, plus nodes whose reader thread died and
        whose path came back (a Bluetooth board reconnecting on the same
        node); closes devices that are gone. Returns ``(added, removed)``
        display lines. Safe to call while reader threads run.
        """
        if self._stop.is_set():
            return [], []
        want = {path: name for path, name, phys in self._select(config_devices)}
        added: list[str] = []
        for path, name in want.items():
            entry = self._live.get(path)
            if entry is not None and entry[1].is_alive():
                continue
            if entry is not None:
                self._close(path)
            if self._open(path, name):
                added.append(f"{name}  [{path}]")
        removed: list[str] = []
        for path in list(self._live):
            if path not in want:
                dev = self._live[path][0]
                removed.append(f"{dev.name}  [{path}]")
                self._close(path)
        return added, removed

    def _read_loop(self, dev: InputDevice) -> None:
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([dev], [], [], 0.3)
                if not r:
                    continue
                for event in dev.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    if event.value == 1 or (
                            self.play_on_repeat and event.value == 2):
                        try:
                            self.handler(event.code, event.value, dev.name)
                        except Exception:
                            pass
            except OSError:
                break

    def stop(self) -> None:
        self._stop.set()
        for path in list(self._live):
            self._close(path)
        self.opened = []
