"""Global hotkey listener."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Optional

from pynput import keyboard

from .compat import MASK_CONTROL, MASK_SHIFT, modifier_is_pressed
from .log import log

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


_CTRL_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
_SHIFT_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
_MODIFIER_WINDOW_SECONDS = 0.5  # Modifier must be active within this window of hotkey release


class HotkeyListener:
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
        self._key_name = key_name
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end

        self._lock = threading.Lock()
        self._pressed = False
        self._ctrl_held = False
        self._ctrl_last_seen: float = 0.0
        self._shift_held = False
        self._shift_last_seen: float = 0.0
        self._listener: Optional[keyboard.Listener] = None

    def set_key(self, key_name: str) -> None:
        """Change the hotkey at runtime (no restart needed)."""
        if key_name not in KEY_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(KEY_MAP)}")
        self._target_key = KEY_MAP[key_name]
        self._key_name = key_name

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
        """Check if a modifier was active: currently held, OS says so, or within window."""
        return (
            held
            or modifier_is_pressed(mask)
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
            # Run off pynput thread so key release events aren't blocked
            threading.Thread(
                target=self._on_hold_start, daemon=True,
                name="hotkey-start",
            ).start()

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
                ctrl_delta = now - self._ctrl_last_seen
                shift_delta = now - self._shift_last_seen
                auto_send = self._modifier_recent(
                    self._ctrl_held, self._ctrl_last_seen,
                    MASK_CONTROL, now,
                )
                command_mode = self._modifier_recent(
                    self._shift_held, self._shift_last_seen,
                    MASK_SHIFT, now,
                )
                cd, sd = ctrl_delta, shift_delta
                log("hotkey", f"Release: send={auto_send} ctrl={cd:.2f}s cmd={command_mode} shift={sd:.2f}s")
                should_fire = True

        if should_fire:
            threading.Thread(
                target=self._on_hold_end, args=(auto_send, command_mode),
                daemon=True, name="hotkey-end",
            ).start()

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
