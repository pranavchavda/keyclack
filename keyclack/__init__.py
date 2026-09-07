"""keyclack - mechanical keyboard sound effects on every key press.

A Klack-style background daemon for Linux (Omarchy / Hyprland / Wayland).

Capture: raw /dev/input events via python-evdev (works on Wayland, no root
when the user is in the `input` group).  Audio: low-latency PortAudio/PipeWire
mixing of real recorded mechanical-switch samples.
"""

__version__ = "0.1.0"
APP = "keyclack"
