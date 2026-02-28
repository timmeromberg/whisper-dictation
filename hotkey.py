"""Global right-Option hotkey listener."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Optional

from pynput import keyboard

KEY_MAP = {
    "left_option": keyboard.Key.alt_l,
    "alt_l": keyboard.Key.alt_l,
    "left_alt": keyboard.Key.alt_l,
    "right_option": keyboard.Key.alt_r,
    "alt_r": keyboard.Key.alt_r,
    "right_alt": keyboard.Key.alt_r,
    "right_command": keyboard.Key.cmd_r,
    "right_shift": keyboard.Key.shift_r,
    "left_command": keyboard.Key.cmd_l,
    "left_shift": keyboard.Key.shift_l,
}


class RightOptionHotkeyListener:
    """Listens for hold/release of right Option and ignores key-repeat noise."""

    def __init__(
        self,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[], None],
        key_name: str = "right_option",
    ) -> None:
        if key_name not in KEY_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(KEY_MAP)}")

        self._target_key = KEY_MAP[key_name]
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end

        self._lock = threading.Lock()
        self._pressed = False
        self._listener: Optional[keyboard.Listener] = None

    def _matches(self, key: keyboard.KeyCode | keyboard.Key | None) -> bool:
        if key == self._target_key:
            return True
        # KeyCode vk comparison for special keys like Fn/Globe
        if (
            isinstance(key, keyboard.KeyCode)
            and isinstance(self._target_key, keyboard.KeyCode)
            and key.vk is not None
            and self._target_key.vk is not None
            and key.vk == self._target_key.vk
        ):
            return True
        return False

    def _handle_press(self, key: keyboard.KeyCode | keyboard.Key | None) -> None:
        if not self._matches(key):
            return

        should_fire = False
        with self._lock:
            if not self._pressed:
                self._pressed = True
                should_fire = True

        if should_fire:
            self._on_hold_start()

    def _handle_release(self, key: keyboard.KeyCode | keyboard.Key | None) -> None:
        if not self._matches(key):
            return

        should_fire = False
        with self._lock:
            if self._pressed:
                self._pressed = False
                should_fire = True

        if should_fire:
            self._on_hold_end()

    def start(self) -> None:
        with self._lock:
            if self._listener is not None:
                return

            self._listener = keyboard.Listener(
                on_press=self._handle_press,
                on_release=self._handle_release,
            )
            self._listener.start()

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
            self._pressed = False

        if listener is not None:
            listener.stop()
