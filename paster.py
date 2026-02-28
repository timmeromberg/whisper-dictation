"""Clipboard + simulated paste helpers."""

from __future__ import annotations

import threading
import time

import pyperclip
import Quartz
from pynput.keyboard import Controller, Key

# macOS virtual key code for Return
_VK_RETURN = 36


def _post_key(vk: int) -> None:
    """Post a key down + key up CGEvent directly (Hammerspoon-style)."""
    down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


class TextPaster:
    """Copy text to clipboard and issue Cmd+V."""

    def __init__(self, paste_delay_seconds: float = 0.05, auto_send: bool = False) -> None:
        self.paste_delay_seconds = paste_delay_seconds
        self.auto_send = auto_send
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

            if self.auto_send:
                time.sleep(0.3)
                _post_key(_VK_RETURN)
