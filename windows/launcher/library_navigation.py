from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal

from library_grid import GameGridView as BaseGameGridView
from library_grid import GameListView as BaseGameListView


class _NavigationMixin:
    """Separate cursor movement from opening a game.

    app_v10's original library view used one signal for both jobs. That made
    D-pad/arrow movement indistinguishable from Enter/A/click activation and
    also made filtered Big Picture rows easy to map to the wrong hidden list
    row. This mixin keeps the visual widgets intact while exposing two clear
    UI events.
    """

    selectionChanged = Signal(int)
    gameActivated = Signal(int)

    def set_items(self, rows):
        super().set_items(rows)
        # The visual capsule/row itself normally owns keyboard focus. Install
        # the view as an event filter so physical arrow keys follow the exact
        # same path as controller navigation instead of getting swallowed by
        # QFrame's default focus handling.
        for widget in self._items.values():
            widget.installEventFilter(self)

    def _source_row(self, key: str) -> int | None:
        widget = self._items.get(key)
        if widget is None:
            return None
        return int(widget.row)

    def _set_current_key(self, key: str) -> None:
        changed = self._current_key != key
        self._current_key = key
        if changed:
            row = self._source_row(key)
            if row is not None:
                self.selectionChanged.emit(row)

    def _activate(self, key: str) -> None:
        row = self._source_row(key)
        if row is None:
            return
        if self._current_key != key:
            self._current_key = key
            self.selectionChanged.emit(row)
        self.gameActivated.emit(row)

    def _move_selection_by(self, delta: int) -> None:
        ordered = sorted(
            (widget for key, widget in self._items.items() if not key.startswith("__skeleton_")),
            key=lambda widget: widget.row,
        )
        if not ordered:
            return
        index = next(
            (i for i, widget in enumerate(ordered) if widget.key == self._current_key),
            0,
        )
        new_index = max(0, min(len(ordered) - 1, index + delta))
        target = ordered[new_index]
        self._current_key = target.key
        self.selectionChanged.emit(int(target.row))

    def set_source_rows(self, mapping: dict[str, int]) -> None:
        """Restore the hidden QListWidget's real row numbers after filtering."""
        for key, widget in self._items.items():
            if key in mapping:
                widget.row = int(mapping[key])

    def contains_source_row(self, row: int) -> bool:
        return any(
            not key.startswith("__skeleton_") and int(widget.row) == int(row)
            for key, widget in self._items.items()
        )

    def first_source_row(self) -> int | None:
        real = [
            widget for key, widget in self._items.items()
            if not key.startswith("__skeleton_")
        ]
        if not real:
            return None
        return int(min(real, key=lambda widget: widget.row).row)

    def activate_current(self) -> bool:
        if self._current_key is None or self._current_key not in self._items:
            first = self.first_source_row()
            if first is None:
                return False
            target = next(
                (
                    widget for key, widget in self._items.items()
                    if not key.startswith("__skeleton_") and int(widget.row) == first
                ),
                None,
            )
            if target is None:
                return False
            self._current_key = target.key
        self._activate(self._current_key)
        return True

    def move_direction(self, direction: str) -> bool:
        columns = max(1, int(self._columns()))
        delta = {
            "left": -1,
            "right": 1,
            "up": -columns,
            "down": columns,
        }.get(direction)
        if delta is None:
            return False
        self._move_selection_by(delta)
        return True

    def eventFilter(self, watched, event):
        if watched in self._items.values() and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                if hasattr(watched, "key"):
                    self._current_key = watched.key
                self.activate_current()
                return True
            direction = {
                Qt.Key_Left: "left",
                Qt.Key_Right: "right",
                Qt.Key_Up: "up",
                Qt.Key_Down: "down",
            }.get(key)
            if direction is not None:
                if hasattr(watched, "key"):
                    self._current_key = watched.key
                self.move_direction(direction)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activate_current()
            return
        direction = {
            Qt.Key_Left: "left",
            Qt.Key_Right: "right",
            Qt.Key_Up: "up",
            Qt.Key_Down: "down",
        }.get(key)
        if direction is not None:
            self.move_direction(direction)
            return
        super().keyPressEvent(event)


class GameListView(_NavigationMixin, BaseGameListView):
    pass


class GameGridView(_NavigationMixin, BaseGameGridView):
    pass
