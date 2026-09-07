"""Configuration for keyclack.

Config lives at ~/.config/keyclack/config.toml  (XDG_CONFIG_HOME aware).
A default file is written on first use so the app is self-describing.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field

from . import APP


def _xdg(name: str, default: str) -> str:
    env = os.environ.get(name)
    if env and env.strip():
        return env.strip()
    return os.path.expanduser(default)


CONFIG_DIR = os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), APP)
DATA_DIR = os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), APP)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.toml")
DEFAULT_PACK_DIR = os.path.join(DATA_DIR, "packs")

# Packs bundled with the package (shipped inside keyclack/packs/). Used as a
# fallback when a fresh install has not yet populated the XDG pack dir.
BUNDLED_PACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "packs")


def pack_dirs(configured: str) -> list:
    """Ordered list of directories to search for packs.

    The configured (user-writable) directory comes first so a user can drop in
    or override packs; the bundled directory is the fallback so the app works
    out of the box.
    """
    configured = os.path.abspath(os.path.expanduser(configured))
    dirs = [configured]
    bundled = os.path.abspath(BUNDLED_PACK_DIR)
    if bundled not in dirs and os.path.isdir(bundled):
        dirs.append(bundled)
    return dirs


def find_pack_dir(configured: str, pack: str) -> str | None:
    """Return the first directory containing `pack`, or None."""
    for d in pack_dirs(configured):
        if os.path.isfile(os.path.join(d, pack, "manifest.json")):
            return os.path.join(d, pack)
    return None


def list_available_packs(configured: str) -> dict:
    """Map pack id -> its directory, searching configured then bundled dirs.
    Configured dir wins when the same pack exists in both."""
    result: dict = {}
    for d in reversed(pack_dirs(configured)):
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if os.path.isfile(os.path.join(d, name, "manifest.json")):
                result[name] = os.path.join(d, name)
    return result

DEFAULT_CONFIG_TEXT = """\
# keyclack configuration
#
# Run `keyclack help` for the CLI.  After editing, restart the daemon
# (`keyclack restart` when installed as a service, or Ctrl-C + `keyclack run`).

# Master on/off switch (can also be toggled at runtime: SIGUSR1).
enabled = true

# Global output volume 0.0 - 1.0.
volume = 0.9

# Which sound pack to use (name of a directory inside pack_dir).
# Installed packs: see `keyclack packs`.
pack = "cherry-mx-blue"

# Directory containing pack folders.  Each pack folder has a manifest.json
# plus .wav files (see any installed pack for the layout).
pack_dir = "{pack_dir}"

# Audio device selection.  "default" uses your system default sink (PipeWire).
# Or name an exact PortAudio device, e.g. "Ryzen HD Audio Controller ...".
audio_device = "default"
# Sample rate used for the output stream.
sample_rate = 48000

# How to pick keyboards to listen to.
#   "auto"            -> every keyboard device that has letter keys
#   explicit list     -> only devices whose name or /dev/input path contains
#                        ANY of these strings, e.g. ["BN006"] or ["event2"]
devices = "auto"

# Play a sound on press only (default).  Set true to also emit on the auto-
# repeat of a held key (usually *not* wanted - sounds like machine-gunning).
play_on_repeat = false

# Modifier keys (Shift/Ctrl/Alt/Super) also make a sound when pressed.
include_modifiers = true

# Advance the press/release modelling: these packs only carry a press sound,
# so the natural "clack" covers the whole press+release.  Nothing to tune here
# unless a pack adds release samples later.
"""


@dataclass
class Config:
    enabled: bool = True
    volume: float = 0.9
    pack: str = "cherry-mx-blue"
    pack_dir: str = DEFAULT_PACK_DIR
    audio_device: str = "default"
    sample_rate: int = 48000
    devices: object = "auto"  # str or list[str]
    play_on_repeat: bool = False
    include_modifiers: bool = True
    # internal
    _path: str = field(default=CONFIG_FILE, init=False)

    @classmethod
    def load(cls) -> "Config":
        ensure_defaults()
        try:
            with open(CONFIG_FILE, "rb") as fh:
                raw = tomllib.load(fh)
        except FileNotFoundError:
            raw = {}
        except tomllib.TOMLDecodeError as exc:
            print(f"keyclack: config {CONFIG_FILE} is invalid TOML: {exc}\n"
                  f"Falling back to defaults.", file=sys.stderr)
            raw = {}

        def _get(*path, default=None):
            node = raw
            for key in path:
                if not isinstance(node, dict) or key not in node:
                    return default
                node = node[key]
            return node

        devices = _get("devices", default="auto")
        cfg = cls(
            enabled=bool(_get("enabled", default=True)),
            volume=float(_get("volume", default=0.9)),
            pack=str(_get("pack", default="cherry-mx-blue")),
            pack_dir=str(_get("pack_dir", default=DEFAULT_PACK_DIR)),
            audio_device=str(_get("audio_device", default="default")),
            sample_rate=int(_get("sample_rate", default=48000)),
            devices=devices,
            play_on_repeat=bool(_get("play_on_repeat", default=False)),
            include_modifiers=bool(_get("include_modifiers", default=True)),
        )
        cfg._path = CONFIG_FILE
        return cfg

    def save(self, path: str | None = None) -> None:
        path = path or self._path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"enabled = {str(self.enabled).lower()}\n")
            fh.write(f"volume = {self.volume:g}\n")
            fh.write(f'pack = "{self.pack}"\n')
            fh.write(f'pack_dir = "{self.pack_dir}"\n')
            fh.write(f'audio_device = "{self.audio_device}"\n')
            fh.write(f"sample_rate = {self.sample_rate}\n")
            if self.devices == "auto" or isinstance(self.devices, str):
                fh.write(f'devices = "auto"\n')
            else:
                fh.write(f"devices = {self.devices!r}\n")
            fh.write(f"play_on_repeat = {str(self.play_on_repeat).lower()}\n")
            fh.write(f"include_modifiers = {str(self.include_modifiers).lower()}\n")

    def pack_path(self) -> str:
        return os.path.join(self.pack_dir, self.pack)

    def resolve_pack_path(self) -> str | None:
        """Absolute path to the active pack dir, searching configured then
        bundled dirs so a fresh install works out of the box."""
        return find_pack_dir(self.pack_dir, self.pack)


def ensure_defaults() -> None:
    """Write a default config + comment header if none exists yet."""
    if os.path.exists(CONFIG_FILE):
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DEFAULT_PACK_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
        fh.write(DEFAULT_CONFIG_TEXT.format(pack_dir=DEFAULT_PACK_DIR))
