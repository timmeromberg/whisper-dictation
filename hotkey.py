"""Global hotkey listener."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Optional

import Quartz
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


def _ctrl_is_pressed() -> bool:
    """Check if Control is physically held right now (Quartz flag check)."""
    for source in (
        Quartz.kCGEventSourceStateHIDSystemState,
        Quartz.kCGEventSourceStateCombinedSessionState,
    ):
        flags = Quartz.CGEventSourceFlagsState(source)
        if flags & Quartz.kCGEventFlagMaskControl:
            return True
    return False


_CTRL_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
_CTRL_WINDOW_SECONDS = 0.5  # Control must be held within this window of hotkey release


class RightOptionHotkeyListener:
    """Listens for hold/release of the hotkey and ignores key-repeat noise."""

    def __init__(
        self,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[bool], None],
        key_name: str = "right_option",
    ) -> None:
        if key_name not in KEY_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(KEY_MAP)}")

        self._target_key = KEY_MAP[key_name]
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end

        self._lock = threading.Lock()
        self._pressed = False
        self._ctrl_held = False
        self._ctrl_last_seen: float = 0.0  # monotonic timestamp of last ctrl press/hold
        self._listener: Optional[keyboard.Listener] = None

    def _matches(self, key: keyboard.KeyCode | keyboard.Key | None) -> bool:
        if key == self._target_key:
            return True
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
        if key in _CTRL_KEYS:
            with self._lock:
                self._ctrl_held = True
                self._ctrl_last_seen = time.monotonic()
            return

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
        if key in _CTRL_KEYS:
            with self._lock:
                self._ctrl_held = False
            return

        if not self._matches(key):
            return

        should_fire = False
        ctrl_recent = False
        with self._lock:
            if self._pressed:
                self._pressed = False
                now = time.monotonic()
                # Control counts if: currently held, OR was held within the last 500ms
                ctrl_recent = (
                    self._ctrl_held
                    or _ctrl_is_pressed()
                    or (now - self._ctrl_last_seen) < _CTRL_WINDOW_SECONDS
                )
                should_fire = True

        if should_fire:
            self._on_hold_end(ctrl_recent)

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
