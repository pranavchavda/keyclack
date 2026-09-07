"""Map raw evdev keycodes to sound roles.

Each recorded pack carries a small set of press samples:
    key / key2 : generic keys (we alternate for variety)
    space      : KEY_SPACE
    enter      : KEY_ENTER / KEY_KPENTER
    delete     : KEY_BACKSPACE / KEY_DELETE
Everything else (letters, digits, punctuation, arrows, F-keys...) uses the
generic key sample.
"""

from __future__ import annotations

from evdev import ecodes


def key_name(code: int) -> str:
    return getattr(ecodes, "KEY", {}).get(code, f"KEY_{code}")


# ---- roles ---------------------------------------------------------------

ROLE_KEY = "key"
ROLE_SPACE = "space"
ROLE_ENTER = "enter"
ROLE_DELETE = "delete"

_SPACE = {ecodes.KEY_SPACE}
_ENTER = {ecodes.KEY_ENTER, ecodes.KEY_KPENTER}
_DELETE = {ecodes.KEY_BACKSPACE, ecodes.KEY_DELETE, ecodes.KEY_KPPLUSMINUS}
# KPPLUSMINUS is not delete; keep delete set tight:
_DELETE = {ecodes.KEY_BACKSPACE, ecodes.KEY_DELETE}

_MODIFIERS = {
    ecodes.KEY_LEFTSHIFT,
    ecodes.KEY_RIGHTSHIFT,
    ecodes.KEY_LEFTCTRL,
    ecodes.KEY_RIGHTCTRL,
    ecodes.KEY_LEFTALT,
    ecodes.KEY_RIGHTALT,
    ecodes.KEY_LEFTMETA,
    ecodes.KEY_RIGHTMETA,
    ecodes.KEY_COMPOSE,
}

# Caps-lock is a toggle but physically a full key that clacks; treated as a
# normal key (not a "modifier") so it is only silenced if we ever mute all
# keys, which we don't.


class KeyRoles:
    """Resolves a keycode to a role name, honouring runtime switches."""

    def __init__(self, include_modifiers: bool = True):
        self.include_modifiers = include_modifiers
        self._press_count = 0  # to alternate key/key2

    def resolve(self, code: int) -> str | None:
        """Return a role string, or None if the press should be silent."""
        if code in _SPACE:
            return ROLE_SPACE
        if code in _ENTER:
            return ROLE_ENTER
        if code in _DELETE:
            return ROLE_DELETE
        if code in _MODIFIERS and not self.include_modifiers:
            return None
        # Normal key: alternate between the pack's key / key2 variants so
        # rapid typing does not sound like a loop of one identical click.
        self._press_count += 1
        if self._press_count % 2 == 0:
            return "key2"
        return ROLE_KEY
