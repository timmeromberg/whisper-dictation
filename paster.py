"""Clipboard + simulated paste helpers."""

from __future__ import annotations

import threading
import time

import pyperclip
import Quartz
from AppKit import NSWorkspace
from pynput.keyboard import Controller, Key

# macOS virtual key code for Return
_VK_RETURN = 36

# Bundle IDs of apps where auto_send should fire
_TERMINAL_BUNDLES = {
    "com.apple.Terminal",
    "com.googlecode.iterm2",
    "com.jetbrains.intellij",
    "com.jetbrains.intellij.ce",
    "com.jetbrains.pycharm",
    "com.jetbrains.pycharm.ce",
    "com.jetbrains.WebStorm",
    "com.jetbrains.CLion",
    "com.jetbrains.goland",
    "com.jetbrains.rider",
    "com.jetbrains.rubymine",
    "com.jetbrains.PhpStorm",
    "com.jetbrains.datagrip",
    "net.kovidgoyal.kitty",
    "io.alacritty",
    "com.github.wez.wezterm",
    "dev.warp.Warp-Stable",
    "co.zeit.hyper",
    "com.microsoft.VSCode",
}


def _post_key(vk: int) -> None:
    """Post a key down + key up CGEvent directly (Hammerspoon-style)."""
    down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def _frontmost_is_terminal() -> bool:
    """Check if the frontmost app is a terminal/IDE."""
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return False
    bundle_id = app.bundleIdentifier() or ""
    return bundle_id in _TERMINAL_BUNDLES


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

            if self.auto_send and _frontmost_is_terminal():
                time.sleep(0.3)
                _post_key(_VK_RETURN)
