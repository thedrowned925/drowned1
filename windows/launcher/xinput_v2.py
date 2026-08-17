from __future__ import annotations

from PySide6.QtCore import Signal

import xinput as legacy


class GamepadPoller(legacy.GamepadPoller):
    """Big Picture controller layer with robust XInput slot discovery.

    XInput exposes four controller slots. The previous poller only queried
    slot 0, so a perfectly valid controller assigned to slots 1-3 appeared
    disconnected. This version scans all four slots, remembers the active
    one, reconnects automatically, and emits separate LB/RB tab actions.
    """

    controllerChanged = Signal(bool, int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_index: int | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def active_index(self) -> int | None:
        return self._active_index

    def _set_connection(self, connected: bool, index: int = -1) -> None:
        if self._connected == connected and self._active_index == (index if connected else None):
            return
        self._connected = connected
        self._active_index = index if connected else None
        self.controllerChanged.emit(connected, index)

    def _read_controller(self):
        # Keep polling the current slot first so normal input costs one call.
        if self._active_index is not None:
            pad = self._reader.get_state(self._active_index)
            if pad is not None:
                return self._active_index, pad

        for index in range(4):
            if index == self._active_index:
                continue
            pad = self._reader.get_state(index)
            if pad is not None:
                return index, pad
        return None, None

    def _poll(self) -> None:
        if not self._is_active():
            return

        index, pad = self._read_controller()
        if pad is None:
            if self._connected:
                self._set_connection(False)
            self._prev_buttons = 0
            self._repeat_direction = None
            self._repeat_elapsed_ms = 0
            return

        self._set_connection(True, int(index))
        self._process_v2(pad.wButtons, pad.sThumbLX, pad.sThumbLY)

    def _process_v2(self, buttons: int, lx: int, ly: int) -> None:
        pressed = buttons & ~self._prev_buttons
        self._prev_buttons = buttons

        if pressed & legacy.BTN_A:
            self.action.emit("activate")
        if pressed & legacy.BTN_B:
            self.action.emit("back")
        if pressed & legacy.LEFT_SHOULDER:
            self.action.emit("previous_tab")
        if pressed & legacy.RIGHT_SHOULDER:
            self.action.emit("next_tab")

        # The footer labels START as the window/Big Picture control, so make
        # it a normal one-press action instead of a hidden hold-and-release
        # gesture.
        if pressed & legacy.START:
            self.action.emit("toggle_big_picture")

        direction = self._direction(buttons, lx, ly)
        if direction != self._repeat_direction:
            self._repeat_direction = direction
            self._repeat_elapsed_ms = 0
            if direction:
                self.action.emit(direction)
        elif direction:
            self._repeat_elapsed_ms += self._interval_ms
            over = self._repeat_elapsed_ms - legacy._REPEAT_INITIAL_DELAY_MS
            if over >= 0 and over % legacy._REPEAT_INTERVAL_MS < self._interval_ms:
                self.action.emit(direction)
