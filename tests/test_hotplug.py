"""Hotplug regression tests: keyboards that appear after Capture starts.

Reproduces the Bluetooth failure: the daemon starts at login, the board
connects minutes later (and reconnects after every sleep). A startup-only
device snapshot never sees it, so no sounds play. Requires /dev/uinput,
exactly like `keyclack test`.
"""

import os
import time

import pytest

from keyclack.capture import Capture
from keyclack.uinput_tools import TypingKeyboard

pytestmark = pytest.mark.skipif(
    not os.access("/dev/uinput", os.W_OK), reason="needs writable /dev/uinput")

# Restrict capture to the virtual board only; real keyboards stay out.
FILTER = ["keyclack test keyboard"]


def _make_capture(pressed):
    return Capture(handler=lambda c, v, n: pressed.append(n),
                   include_synthetic=True)


def test_keyboard_joining_late_is_captured_and_delivers_events():
    pressed = []
    cap = _make_capture(pressed)
    try:
        assert cap.start(FILTER) == 0  # board not connected yet

        tk = TypingKeyboard("hotplug")  # the board connects late
        try:
            time.sleep(0.3)
            added, removed = cap.rescan(FILTER)
            assert len(added) == 1 and "keyclack test keyboard" in added[0]
            assert removed == []
            assert len(cap.opened) == 1

            tk.type("hi", delay=0.05)
            time.sleep(0.6)
            assert len(pressed) >= 2  # late joiner actually sounds

            # Nothing changed -> rescan is a no-op, not churn.
            added, removed = cap.rescan(FILTER)
            assert added == [] and removed == []
        finally:
            tk.close()
    finally:
        cap.stop()


def test_keyboard_disconnect_then_reconnect_needs_no_restart():
    pressed = []
    cap = _make_capture(pressed)
    try:
        tk = TypingKeyboard("hotplug")  # connected before start: baseline path
        time.sleep(0.3)
        cap.start(FILTER)
        assert len(cap.opened) == 1

        tk.close()  # BT sleep / walk away
        time.sleep(0.3)
        added, removed = cap.rescan(FILTER)
        assert added == []
        assert len(removed) == 1 and "keyclack test keyboard" in removed[0]
        assert cap.opened == []

        tk2 = TypingKeyboard("hotplug")  # reconnects, maybe on a new node
        try:
            time.sleep(0.3)
            added, removed = cap.rescan(FILTER)
            assert len(added) == 1 and removed == []
            assert len(cap.opened) == 1

            tk2.type("hi", delay=0.05)
            time.sleep(0.6)
            assert len(pressed) >= 2  # reconnected board sounds again
        finally:
            tk2.close()
    finally:
        cap.stop()
