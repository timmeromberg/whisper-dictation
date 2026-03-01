"""Clipboard + simulated paste helpers."""

from __future__ import annotations

import threading
import time

import pyperclip
from pynput.keyboard import Controller

from compat import PASTE_MODIFIER_KEY, TERMINAL_APP_IDS, VK_RETURN, frontmost_app_id, post_keycode
from log import log


class TextPaster:
    """Copy text to clipboard and simulate paste."""

    def __init__(self, paste_delay_seconds: float = 0.05) -> None:
        self.paste_delay_seconds = paste_delay_seconds
        self._keyboard = Controller()
        self._lock = threading.Lock()

    def paste(self, text: str, auto_send: bool = False) -> None:
        text = text.strip()
        if not text:
            return

        with self._lock:
            # Save current clipboard so we can restore it after pasting.
            # This prevents accidental re-paste of dictated text.
            try:
                saved_clipboard = pyperclip.paste()
            except Exception:
                saved_clipboard = ""

            log("paste", f"Copying {len(text)} chars to clipboard")
            pyperclip.copy(text)
            time.sleep(self.paste_delay_seconds)
            log("paste", "Sending paste shortcut")
            with self._keyboard.pressed(PASTE_MODIFIER_KEY):
                self._keyboard.press("v")
                self._keyboard.release("v")

            if auto_send:
                app = frontmost_app_id()
                is_terminal = app in TERMINAL_APP_IDS
                log("paste", f"Auto-send check: app={app}, terminal={is_terminal}")
                if is_terminal:
                    time.sleep(0.3)
                    log("paste", "Sending Return")
                    post_keycode(VK_RETURN)

            # Restore previous clipboard after a brief delay for the paste
            # to be processed by the target application.
            time.sleep(0.1)
            try:
                pyperclip.copy(saved_clipboard)
            except Exception:
                pass
