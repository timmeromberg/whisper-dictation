"""Clipboard + simulated paste helpers."""

from __future__ import annotations

import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key


class TextPaster:
    """Copy text to clipboard and issue Cmd+V."""

    def __init__(self, paste_delay_seconds: float = 0.05) -> None:
        self.paste_delay_seconds = paste_delay_seconds
        self._keyboard = Controller()
        self._lock = threading.Lock()

    def paste(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        with self._lock:
            pyperclip.copy(text)
            time.sleep(self.paste_delay_seconds)
            with self._keyboard.pressed(Key.cmd):
                self._keyboard.press("v")
                self._keyboard.release("v")
