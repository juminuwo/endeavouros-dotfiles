#!/usr/bin/env python3
"""Map MMO mouse (Redragon Impact M908) side buttons to i3 workspaces.

Grabs exclusive access to the mouse's keyboard interface so the side
button keypresses don't leak to other applications.
"""

import subprocess
import sys
import time

import evdev

DEVICE_PATH = "/dev/input/by-id/usb-04d9_USB_Gaming_Mouse-if01-event-kbd"

# evdev keycode -> workspace number
# (evdev keycodes = X11 keycodes - 8)
KEYCODE_TO_WORKSPACE = {
    104: "1",   # KEY_PAGEUP
    106: "2",   # KEY_RIGHT
    109: "3",   # KEY_PAGEDOWN
    13:  "4",   # KEY_EQUAL
    103: "5",   # KEY_UP
    21:  "6",   # KEY_Y
    108: "7",   # KEY_DOWN
    26:  "8",   # KEY_LEFTBRACE
    102: "9",   # KEY_HOME
    105: "10",  # KEY_LEFT
    107: "11",  # KEY_END
    12:  "12",  # KEY_MINUS
}


def switch_workspace(ws):
    subprocess.Popen(
        ["i3-msg", f"workspace {ws}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    while True:
        try:
            device = evdev.InputDevice(DEVICE_PATH)
            device.grab()
            print(f"Grabbed {device.name} at {device.path}", flush=True)

            for event in device.read_loop():
                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    ws = KEYCODE_TO_WORKSPACE.get(event.code)
                    if ws:
                        switch_workspace(ws)

        except FileNotFoundError:
            print("Mouse not found, retrying in 5s...", flush=True)
            time.sleep(5)
        except OSError as e:
            print(f"Device error: {e}, retrying in 2s...", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
