"""Clipboard + simulated paste helpers."""

from __future__ import annotations

import subprocess
import threading
import time

import pyperclip
import Quartz
from pynput.keyboard import Controller, Key

from commands import VK_RETURN
from log import log

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


def _frontmost_bundle_id() -> str:
    """Get frontmost app bundle ID via osascript (always fresh)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get bundle identifier of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return ""


class TextPaster:
    """Copy text to clipboard and issue Cmd+V."""

    def __init__(self, paste_delay_seconds: float = 0.05) -> None:
        self.paste_delay_seconds = paste_delay_seconds
        self._keyboard = Controller()
        self._lock = threading.Lock()

    def paste(self, text: str, auto_send: bool = False) -> None:
        text = text.strip()
        if not text:
            return

        with self._lock:
            log("paste", f"Copying {len(text)} chars to clipboard")
            pyperclip.copy(text)
            time.sleep(self.paste_delay_seconds)
            log("paste", "Sending Cmd+V")
            with self._keyboard.pressed(Key.cmd):
                self._keyboard.press("v")
                self._keyboard.release("v")

            if auto_send:
                bundle = _frontmost_bundle_id()
                is_terminal = bundle in _TERMINAL_BUNDLES
                log("paste", f"Auto-send check: bundle={bundle}, terminal={is_terminal}")
                if is_terminal:
                    time.sleep(0.3)
                    log("paste", "Sending Return")
                    _post_key(VK_RETURN)
