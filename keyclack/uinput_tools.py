"""Inject synthetic typing through a virtual uinput keyboard.

Used by `keyclack test` to exercise the full capture -> audio pipeline without
the user touching their physical keyboard.  Requires write access to
/dev/uinput (group `input`, which the user is in).

Important: the UInput device is created in __init__ (so it exists in
/dev/input before the Capture threads enumerate devices), and typing happens
afterwards through the already-open handle.
"""

from __future__ import annotations

import time

from evdev import UInput, ecodes


def _charmap(char: str):
    """Return (keycode, shift) for a printable char in our supported set."""
    if char.islower():
        return getattr(ecodes, "KEY_" + char.upper()), False
    if char.isdigit():
        code = ecodes.KEY_0 if char == "0" else ecodes.KEY_1 + (int(char) - 1)
        return code, False
    if char.isupper():
        return getattr(ecodes, "KEY_" + char.upper()), True
    return {
        " ": (ecodes.KEY_SPACE, False),
        "\n": (ecodes.KEY_ENTER, False),
        "\t": (ecodes.KEY_TAB, False),
        ".": (ecodes.KEY_DOT, False),
        ",": (ecodes.KEY_COMMA, False),
        "-": (ecodes.KEY_MINUS, False),
        "=": (ecodes.KEY_EQUAL, False),
        ";": (ecodes.KEY_SEMICOLON, False),
        "/": (ecodes.KEY_SLASH, False),
        "'": (ecodes.KEY_APOSTROPHE, False),
        "[": (ecodes.KEY_LEFTBRACE, False),
        "]": (ecodes.KEY_RIGHTBRACE, False),
        "`": (ecodes.KEY_GRAVE, False),
        "\\": (ecodes.KEY_BACKSLASH, False),
        "!": (ecodes.KEY_1, True), "@": (ecodes.KEY_2, True),
        "#": (ecodes.KEY_3, True), "$": (ecodes.KEY_4, True),
        "%": (ecodes.KEY_5, True), "^": (ecodes.KEY_6, True),
        "&": (ecodes.KEY_7, True), "*": (ecodes.KEY_8, True),
        "(": (ecodes.KEY_9, True), ")": (ecodes.KEY_0, True),
        "_": (ecodes.KEY_MINUS, True), "+": (ecodes.KEY_EQUAL, True),
        "{": (ecodes.KEY_LEFTBRACE, True), "}": (ecodes.KEY_RIGHTBRACE, True),
        ":": (ecodes.KEY_SEMICOLON, True), '"': (ecodes.KEY_APOSTROPHE, True),
        "<": (ecodes.KEY_COMMA, True), ">": (ecodes.KEY_DOT, True),
        "?": (ecodes.KEY_SLASH, True), "~": (ecodes.KEY_GRAVE, True),
        "|": (ecodes.KEY_BACKSLASH, True),
    }.get(char)


def _needs_shift(chars: str) -> bool:
    for ch in chars:
        if ch.isupper() or ch in '!@#$%^&*()_+{}:"<>?~|':
            return True
    return False


class TypingKeyboard:
    """A virtual keyboard that exists from construction until close()."""

    def __init__(self, phrase: str, name: str = "keyclack test keyboard"):
        # Declare a full typing layout so the device passes keyclack's
        # "is a real keyboard" heuristic (needs KEY_A, KEY_Z, KEY_ENTER) and
        # so the keys we type are all available.
        codes = set(range(ecodes.KEY_A, ecodes.KEY_M + 1))  # noqa
        codes.update(range(ecodes.KEY_1, ecodes.KEY_0 + 1))
        codes.update(range(ecodes.KEY_Q, ecodes.KEY_P + 1))
        codes.update(range(ecodes.KEY_Z, ecodes.KEY_M + 1))
        codes.update({
            ecodes.KEY_SPACE, ecodes.KEY_ENTER, ecodes.KEY_BACKSPACE,
            ecodes.KEY_LEFTSHIFT, ecodes.KEY_TAB, ecodes.KEY_COMMA,
            ecodes.KEY_DOT, ecodes.KEY_SLASH, ecodes.KEY_MINUS,
            ecodes.KEY_EQUAL, ecodes.KEY_LEFTBRACE, ecodes.KEY_RIGHTBRACE,
            ecodes.KEY_SEMICOLON, ecodes.KEY_APOSTROPHE, ecodes.KEY_GRAVE,
            ecodes.KEY_BACKSLASH,
        })
        self._ui = UInput(events={ecodes.EV_KEY: list(codes)}, name=name,
                          bustype=ecodes.BUS_VIRTUAL)

    def type(self, text: str, delay: float = 0.05) -> None:
        ui = self._ui
        for ch in text:
            hit = _charmap(ch)
            if not hit:
                continue
            code, shift = hit
            if shift:
                ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
                ui.syn()
            ui.write(ecodes.EV_KEY, code, 1)
            ui.syn()
            time.sleep(delay)
            ui.write(ecodes.EV_KEY, code, 0)
            ui.syn()
            if shift:
                ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                ui.syn()
            time.sleep(delay * 0.4)

    def close(self) -> None:
        self._ui.close()


def type_text(text: str, delay: float = 0.05) -> None:
    tk = TypingKeyboard(text)
    try:
        tk.type(text, delay)
    finally:
        tk.close()
