"""Windows XInput gamepad polling for the Launcher's Big Picture navigation.

Uses ctypes against the system XInput DLL directly -- no extra pip dependency,
matches this project's Windows-only footprint. Only Xbox/XInput-compatible
controllers are supported (the vast majority of modern pads, including most
PlayStation pads once switched to XInput-compatibility mode).
"""

from __future__ import annotations

import ctypes
import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal

DPAD_UP = 0x0001
DPAD_DOWN = 0x0002
DPAD_LEFT = 0x0004
DPAD_RIGHT = 0x0008
START = 0x0010
BACK = 0x0020
LEFT_THUMB = 0x0040
RIGHT_THUMB = 0x0080
LEFT_SHOULDER = 0x0100
RIGHT_SHOULDER = 0x0200
BTN_A = 0x1000
BTN_B = 0x2000
BTN_X = 0x4000
BTN_Y = 0x8000

_DPAD_MASK = DPAD_UP | DPAD_DOWN | DPAD_LEFT | DPAD_RIGHT

_START_HOLD_SECONDS = 0.6
_REPEAT_INITIAL_DELAY_MS = 350
_REPEAT_INTERVAL_MS = 110


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", XINPUT_GAMEPAD)]


class XInputReader:
    """Thin wrapper around XInputGetState. Safe to construct on non-Windows;
    it simply never finds a controller."""

    _DLL_NAMES = ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll")

    def __init__(self):
        self._dll = self._load_dll() if sys.platform == "win32" else None

    @classmethod
    def _load_dll(cls):
        for name in cls._DLL_NAMES:
            try:
                dll = ctypes.WinDLL(name)
            except OSError:
                continue
            dll.XInputGetState.argtypes = [ctypes.c_uint32, ctypes.POINTER(XINPUT_STATE)]
            dll.XInputGetState.restype = ctypes.c_uint32
            return dll
        return None

    @property
    def available(self) -> bool:
        return self._dll is not None

    def get_state(self, index: int = 0) -> XINPUT_GAMEPAD | None:
        if self._dll is None:
            return None
        state = XINPUT_STATE()
        if self._dll.XInputGetState(index, ctypes.byref(state)) != 0:
            return None
        return state.Gamepad


class GamepadPoller(QObject):
    """Polls one XInput controller on a QTimer and emits discrete UI actions.

    Face/shoulder/Start buttons are edge-detected (fire once per physical
    press). D-pad/left-stick direction uses a typematic repeat: immediate on
    first press, then a repeat delay, then a steady repeat interval while held
    -- lets a user hold a direction to move across a large grid.
    """

    action = Signal(str)  # "up" | "down" | "left" | "right" | "activate" | "back" | "toggle_big_picture" | "switch_view"

    def __init__(self, parent=None, interval_ms: int = 60, deadzone: int = 8000, is_active=None):
        super().__init__(parent)
        self._reader = XInputReader()
        self._interval_ms = interval_ms
        self._deadzone = deadzone
        self._is_active = is_active or (lambda: True)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)

        self._prev_buttons = 0
        self._repeat_direction: str | None = None
        self._repeat_elapsed_ms = 0
        self._start_pressed_at: float | None = None

    @property
    def available(self) -> bool:
        return self._reader.available

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        if not self._is_active():
            return
        pad = self._reader.get_state(0)
        if pad is None:
            self._prev_buttons = 0
            self._repeat_direction = None
            return
        self._process(pad.wButtons, pad.sThumbLX, pad.sThumbLY)

    def _process(self, buttons: int, lx: int, ly: int) -> None:
        pressed = buttons & ~self._prev_buttons
        released = ~buttons & self._prev_buttons
        self._prev_buttons = buttons

        if pressed & BTN_A:
            self.action.emit("activate")
        if pressed & BTN_B:
            self.action.emit("back")
        if pressed & (LEFT_SHOULDER | RIGHT_SHOULDER):
            self.action.emit("switch_view")
        if pressed & START:
            self._start_pressed_at = time.monotonic()
        if released & START and self._start_pressed_at is not None:
            held = time.monotonic() - self._start_pressed_at
            self._start_pressed_at = None
            if held >= _START_HOLD_SECONDS:
                self.action.emit("toggle_big_picture")

        direction = self._direction(buttons, lx, ly)
        if direction != self._repeat_direction:
            self._repeat_direction = direction
            self._repeat_elapsed_ms = 0
            if direction:
                self.action.emit(direction)
        elif direction:
            self._repeat_elapsed_ms += self._interval_ms
            over = self._repeat_elapsed_ms - _REPEAT_INITIAL_DELAY_MS
            if over >= 0 and over % _REPEAT_INTERVAL_MS < self._interval_ms:
                self.action.emit(direction)

    def _direction(self, buttons: int, lx: int, ly: int) -> str | None:
        dpad = buttons & _DPAD_MASK
        if dpad & DPAD_UP:
            return "up"
        if dpad & DPAD_DOWN:
            return "down"
        if dpad & DPAD_LEFT:
            return "left"
        if dpad & DPAD_RIGHT:
            return "right"
        if (lx * lx + ly * ly) ** 0.5 < self._deadzone:
            return None
        if abs(lx) >= abs(ly):
            return "right" if lx > 0 else "left"
        return "up" if ly > 0 else "down"
