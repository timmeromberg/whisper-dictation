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


def _modifier_is_pressed(mask: int) -> bool:
    """Check if a modifier is physically held right now (Quartz flag check)."""
    for source in (
        Quartz.kCGEventSourceStateHIDSystemState,
        Quartz.kCGEventSourceStateCombinedSessionState,
    ):
        flags = Quartz.CGEventSourceFlagsState(source)
        if flags & mask:
            return True
    return False


_CTRL_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
_SHIFT_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
_MODIFIER_WINDOW_SECONDS = 0.5  # Modifier must be active within this window of hotkey release


class RightOptionHotkeyListener:
    """Listens for hold/release of the hotkey and ignores key-repeat noise."""

    def __init__(
        self,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[bool, bool], None],
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
        self._ctrl_last_seen: float = 0.0
        self._shift_held = False
        self._shift_last_seen: float = 0.0
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

    def _modifier_recent(self, held: bool, last_seen: float, mask: int, now: float) -> bool:
        """Check if a modifier was active: currently held, Quartz says so, or within window."""
        return (
            held
            or _modifier_is_pressed(mask)
            or (now - last_seen) < _MODIFIER_WINDOW_SECONDS
        )

    def _handle_press(self, key: keyboard.KeyCode | keyboard.Key | None) -> None:
        if key in _CTRL_KEYS:
            with self._lock:
                self._ctrl_held = True
                self._ctrl_last_seen = time.monotonic()
            return

        if key in _SHIFT_KEYS:
            with self._lock:
                self._shift_held = True
                self._shift_last_seen = time.monotonic()
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
                self._ctrl_last_seen = time.monotonic()
            return

        if key in _SHIFT_KEYS:
            with self._lock:
                self._shift_held = False
                self._shift_last_seen = time.monotonic()
            return

        if not self._matches(key):
            return

        should_fire = False
        auto_send = False
        command_mode = False
        with self._lock:
            if self._pressed:
                self._pressed = False
                now = time.monotonic()
                auto_send = self._modifier_recent(
                    self._ctrl_held, self._ctrl_last_seen,
                    Quartz.kCGEventFlagMaskControl, now,
                )
                command_mode = self._modifier_recent(
                    self._shift_held, self._shift_last_seen,
                    Quartz.kCGEventFlagMaskShift, now,
                )
                should_fire = True

        if should_fire:
            self._on_hold_end(auto_send, command_mode)

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
