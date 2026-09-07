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
    """

    def __init__(self, handler, play_on_repeat: bool = False,
                 include_synthetic: bool = False):
        self.handler = handler
        self.play_on_repeat = play_on_repeat
        self.include_synthetic = include_synthetic
        self._devices: list[InputDevice] = []
        self._threads: list[threading.Thread] = []
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
        chosen = self._select(config_devices)
        for path, name, phys in chosen:
            try:
                dev = InputDevice(path)
            except (OSError, PermissionError) as exc:
                print(f"keyclack: cannot open {path} ({name}): {exc}")
                continue
            try:
                dev.grab()  # not needed for passive read, and would block others
            except Exception:
                pass
            dev.ungrab()
            self._devices.append(dev)
            self.opened.append(f"{name}  [{path}]")
            t = threading.Thread(target=self._read_loop, args=(dev,),
                                 name=f"kbd-{path}", daemon=True)
            self._threads.append(t)
            t.start()
        return len(self._threads)

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
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        self._devices = []
