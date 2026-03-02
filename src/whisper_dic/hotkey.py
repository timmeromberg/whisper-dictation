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
# Grace period for modifier detection: if Ctrl/Shift was released just before
# the hotkey, we still count it. Handles timing races where the listener
# thread misses transient key state on fast key combos.
_MODIFIER_WINDOW_SECONDS = 0.5
# Grace period before a key release triggers hold_end.  Absorbs accidental
# brief lifts that happen when the user pauses mid-dictation.
_RELEASE_DEBOUNCE_SECONDS = 0.3


class HotkeyListener:
    """Listens for hold/release of the hotkey and ignores key-repeat noise."""

    def __init__(
        self,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[bool, bool, float | None], None],
        key_name: str = "right_option",
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        if key_name not in KEY_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(KEY_MAP)}")

        self._target_key = KEY_MAP[key_name]
        self._key_name = key_name
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end
        self._on_cancel = on_cancel

        self._lock = threading.Lock()
        self._pressed = False
        self._ctrl_held = False
        self._ctrl_last_seen: float = 0.0
        self._shift_held = False
        self._shift_last_seen: float = 0.0
        self._release_seq = 0
        self._pressed_started_at: float = 0.0
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
        if key == keyboard.Key.esc:
            should_cancel = False
            with self._lock:
                if self._pressed:
                    self._pressed = False
                    should_cancel = True
            if should_cancel and self._on_cancel is not None:
                threading.Thread(
                    target=self._on_cancel, daemon=True, name="hotkey-cancel",
                ).start()
            return

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
                self._pressed_started_at = time.monotonic()
                self._release_seq += 1
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

        with self._lock:
            if not self._pressed:
                return
            self._release_seq += 1
            seq = self._release_seq
            now = time.monotonic()
            hold_duration_seconds = max(0.0, now - self._pressed_started_at)
            auto_send = self._modifier_recent(
                self._ctrl_held, self._ctrl_last_seen,
                MASK_CONTROL, now,
            )
            command_mode = self._modifier_recent(
                self._shift_held, self._shift_last_seen,
                MASK_SHIFT, now,
            )
            cd = now - self._ctrl_last_seen
            sd = now - self._shift_last_seen
            log(
                "hotkey",
                f"Release: debouncing ({_RELEASE_DEBOUNCE_SECONDS}s)"
                f" send={auto_send} ctrl={cd:.2f}s cmd={command_mode} shift={sd:.2f}s",
            )

        threading.Thread(
            target=self._debounced_release,
            args=(seq, auto_send, command_mode, hold_duration_seconds),
            daemon=True, name="hotkey-debounce",
        ).start()

    def _debounced_release(
        self,
        seq: int,
        auto_send: bool,
        command_mode: bool,
        hold_duration_seconds: float,
    ) -> None:
        """Wait for debounce period, then fire hold_end if key wasn't re-pressed."""
        time.sleep(_RELEASE_DEBOUNCE_SECONDS)
        with self._lock:
            if self._release_seq != seq:
                log("hotkey", "Release debounce cancelled (key re-pressed)")
                return
            self._pressed = False
            self._pressed_started_at = 0.0
        log("hotkey", "Release debounce confirmed — firing hold_end")
        self._on_hold_end(auto_send, command_mode, hold_duration_seconds)

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


# ---------------------------------------------------------------------------
# macOS key codes for NSEvent-based listener
# ---------------------------------------------------------------------------

_NS_KEYCODE_MAP: dict[str, int] = {
    "left_option": 58, "alt_l": 58, "left_alt": 58,
    "right_option": 61, "alt_r": 61, "right_alt": 61,
    "left_command": 55, "right_command": 54,
    "left_shift": 56, "right_shift": 60,
}

# Modifier flag corresponding to each key type
_NS_FLAG_FOR_KEY: dict[int, int] = {
    58: 0x80000,   # NSEventModifierFlagOption
    61: 0x80000,
    55: 0x100000,  # NSEventModifierFlagCommand
    54: 0x100000,
    56: 0x20000,   # NSEventModifierFlagShift
    60: 0x20000,
}

_NS_CTRL_KEYCODES = {59, 62}
_NS_SHIFT_KEYCODES = {56, 60}
_NS_CTRL_FLAG = 0x40000   # NSEventModifierFlagControl
_NS_SHIFT_FLAG = 0x20000  # NSEventModifierFlagShift


class NSEventHotkeyListener:
    """Hotkey listener using macOS NSEvent monitors (main-thread safe).

    Unlike pynput's CGEventTap listener, NSEvent monitors run callbacks on
    the main thread, avoiding the SIGTRAP caused by TSM calls from background
    threads on macOS 14+.  Requires an active NSApplication run loop (rumps).
    """

    def __init__(
        self,
        on_hold_start: Callable[[], None],
        on_hold_end: Callable[[bool, bool, float | None], None],
        key_name: str = "right_option",
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        if key_name not in _NS_KEYCODE_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(_NS_KEYCODE_MAP)}")

        self._target_keycode = _NS_KEYCODE_MAP[key_name]
        self._target_flag = _NS_FLAG_FOR_KEY[self._target_keycode]
        self._key_name = key_name
        self._on_hold_start = on_hold_start
        self._on_hold_end = on_hold_end
        self._on_cancel = on_cancel

        self._lock = threading.Lock()
        self._pressed = False
        self._ctrl_held = False
        self._ctrl_last_seen: float = 0.0
        self._shift_held = False
        self._shift_last_seen: float = 0.0
        self._release_seq = 0  # Incremented on each release to cancel stale debounce timers
        self._pressed_started_at: float = 0.0

        self._global_monitor: object | None = None
        self._local_monitor: object | None = None

    def set_key(self, key_name: str) -> None:
        """Change the hotkey at runtime (no restart needed)."""
        if key_name not in _NS_KEYCODE_MAP:
            raise ValueError(f"Unsupported hotkey '{key_name}'. Supported: {', '.join(_NS_KEYCODE_MAP)}")
        self._target_keycode = _NS_KEYCODE_MAP[key_name]
        self._target_flag = _NS_FLAG_FOR_KEY[self._target_keycode]
        self._key_name = key_name

    def _modifier_recent(self, held: bool, last_seen: float, mask: int, now: float) -> bool:
        """Check if a modifier was active: currently held, OS says so, or within window."""
        return (
            held
            or modifier_is_pressed(mask)
            or (now - last_seen) < _MODIFIER_WINDOW_SECONDS
        )

    def _handle_event(self, event: object) -> None:
        """Dispatch NSEvent by type."""
        event_type: int = event.type()  # type: ignore[attr-defined]
        if event_type == 12:  # NSEventTypeFlagsChanged (modifier key press/release)
            self._handle_flags_changed(event)
        elif event_type == 10:  # NSEventTypeKeyDown
            self._handle_key_down(event)

    def _handle_key_down(self, event: object) -> None:
        """Cancel recording if Escape is pressed while hotkey is held."""
        keycode: int = event.keyCode()  # type: ignore[attr-defined]
        if keycode != 53:  # 53 = Escape key
            return
        should_cancel = False
        with self._lock:
            if self._pressed:
                self._pressed = False
                should_cancel = True
        if should_cancel and self._on_cancel is not None:
            threading.Thread(
                target=self._on_cancel, daemon=True, name="hotkey-cancel",
            ).start()

    def _handle_flags_changed(self, event: object) -> None:
        """Process a modifier key state change."""
        keycode: int = event.keyCode()  # type: ignore[attr-defined]
        flags: int = event.modifierFlags()  # type: ignore[attr-defined]

        # Track Ctrl
        if keycode in _NS_CTRL_KEYCODES:
            with self._lock:
                self._ctrl_held = bool(flags & _NS_CTRL_FLAG)
                self._ctrl_last_seen = time.monotonic()
            return

        # Track Shift (unless Shift IS the target key)
        if keycode in _NS_SHIFT_KEYCODES and keycode != self._target_keycode:
            with self._lock:
                self._shift_held = bool(flags & _NS_SHIFT_FLAG)
                self._shift_last_seen = time.monotonic()
            return

        # Target key
        if keycode != self._target_keycode:
            return

        is_down = bool(flags & self._target_flag)

        if is_down:
            should_fire = False
            with self._lock:
                if not self._pressed:
                    self._pressed = True
                    self._pressed_started_at = time.monotonic()
                    # Cancel any pending debounced release
                    self._release_seq += 1
                    should_fire = True
            if should_fire:
                threading.Thread(
                    target=self._on_hold_start, daemon=True, name="hotkey-start",
                ).start()
        else:
            with self._lock:
                if not self._pressed:
                    return
                self._release_seq += 1
                seq = self._release_seq
                now = time.monotonic()
                hold_duration_seconds = max(0.0, now - self._pressed_started_at)
                auto_send = self._modifier_recent(
                    self._ctrl_held, self._ctrl_last_seen, MASK_CONTROL, now,
                )
                command_mode = self._modifier_recent(
                    self._shift_held, self._shift_last_seen, MASK_SHIFT, now,
                )
                cd = now - self._ctrl_last_seen
                sd = now - self._shift_last_seen
                log(
                "hotkey",
                f"Release: debouncing ({_RELEASE_DEBOUNCE_SECONDS}s)"
                f" send={auto_send} ctrl={cd:.2f}s cmd={command_mode} shift={sd:.2f}s",
            )

            # Debounce: wait briefly, then check if key was re-pressed
            threading.Thread(
                target=self._debounced_release,
                args=(seq, auto_send, command_mode, hold_duration_seconds),
                daemon=True, name="hotkey-debounce",
            ).start()

    def _debounced_release(
        self,
        seq: int,
        auto_send: bool,
        command_mode: bool,
        hold_duration_seconds: float,
    ) -> None:
        """Wait for debounce period, then fire hold_end if key wasn't re-pressed."""
        time.sleep(_RELEASE_DEBOUNCE_SECONDS)
        with self._lock:
            # If seq changed, the key was re-pressed (or released again) — stale
            if self._release_seq != seq:
                log("hotkey", "Release debounce cancelled (key re-pressed)")
                return
            self._pressed = False
            self._pressed_started_at = 0.0
        log("hotkey", "Release debounce confirmed — firing hold_end")
        self._on_hold_end(auto_send, command_mode, hold_duration_seconds)

    def _handle_local_event(self, event: object) -> object:
        """Local monitor wrapper — must return event to pass it along."""
        self._handle_event(event)
        return event

    def start(self) -> None:
        from AppKit import NSEvent  # type: ignore[import-untyped]

        # NSEventMaskFlagsChanged | NSEventMaskKeyDown
        event_mask = (1 << 12) | (1 << 0)

        with self._lock:
            if self._global_monitor is not None:
                return

            self._global_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                event_mask, self._handle_event,
            )
            self._local_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                event_mask, self._handle_local_event,
            )

    def stop(self) -> None:
        from AppKit import NSEvent  # type: ignore[import-untyped]

        with self._lock:
            if self._global_monitor is not None:
                NSEvent.removeMonitor_(self._global_monitor)
                self._global_monitor = None
            if self._local_monitor is not None:
                NSEvent.removeMonitor_(self._local_monitor)
                self._local_monitor = None
            self._pressed = False
