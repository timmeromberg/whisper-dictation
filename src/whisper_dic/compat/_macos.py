"""macOS platform implementations (Quartz, osascript, AppKit)."""

from __future__ import annotations

import subprocess

import Quartz
from pynput.keyboard import Key

from ..log import log

# ---------------------------------------------------------------------------
# Modifier checking (from hotkey.py)
# ---------------------------------------------------------------------------

MASK_CONTROL = Quartz.kCGEventFlagMaskControl
MASK_SHIFT = Quartz.kCGEventFlagMaskShift


def modifier_is_pressed(mask: int) -> bool:
    """Check if a modifier is physically held right now (Quartz flag check)."""
    for source in (
        Quartz.kCGEventSourceStateHIDSystemState,
        Quartz.kCGEventSourceStateCombinedSessionState,
    ):
        flags = Quartz.CGEventSourceFlagsState(source)
        if flags & mask:
            return True
    return False


# ---------------------------------------------------------------------------
# Key simulation (from commands.py + paster.py)
# ---------------------------------------------------------------------------

# macOS virtual key codes
VK_RETURN = 36

VK_MAP = {
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5,
    "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45,
    "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17, "u": 32,
    "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
    "6": 22, "7": 26, "8": 28, "9": 25,
    "return": 36, "tab": 48, "escape": 53, "delete": 51,
    "space": 49, "up": 126, "down": 125, "left": 123, "right": 124,
    "-": 27, "=": 24, "[": 33, "]": 30, "\\": 42, ";": 41,
    "'": 39, ",": 43, ".": 47, "/": 44, "`": 50,
}

FLAG_CTRL = Quartz.kCGEventFlagMaskControl
FLAG_CMD = Quartz.kCGEventFlagMaskCommand
FLAG_SHIFT = Quartz.kCGEventFlagMaskShift
FLAG_ALT = Quartz.kCGEventFlagMaskAlternate


def post_key(vk: int, flags: int = 0) -> None:
    """Post a key event with optional modifier flags via CGEvent."""
    down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
    if flags:
        Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def post_keycode(vk: int) -> None:
    """Post a key down + key up CGEvent (no modifiers)."""
    down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


# ---------------------------------------------------------------------------
# Frontmost app detection (from paster.py)
# ---------------------------------------------------------------------------

TERMINAL_APP_IDS: set[str] = {
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

PASTE_MODIFIER_KEY = Key.cmd


def frontmost_app_id() -> str:
    """Get frontmost app bundle ID via osascript."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get bundle identifier'
             ' of first process whose frontmost is true'],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Notifications & audio (from dictation.py)
# ---------------------------------------------------------------------------


def notify(message: str, title: str = "whisper-dic") -> None:
    """Show a macOS notification banner via osascript."""
    safe_msg = message.replace("\\", "\\\\").replace('"', '\\"').replace("`", "'")
    safe_title = title.replace("\\", "\\\\").replace('"', '\\"').replace("`", "'")
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "{safe_title}"'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as exc:
        log("notify", f"Notification failed: {exc}")


def play_wav_file(path: str) -> None:
    """Play a WAV file via macOS afplay."""
    try:
        subprocess.run(["afplay", path], timeout=5)
    except Exception as exc:
        log("audio", f"Playback failed: {exc}")


# ---------------------------------------------------------------------------
# Accessibility check (from dictation.py)
# ---------------------------------------------------------------------------


def check_accessibility() -> list[str]:
    """Check macOS permissions. Returns list of missing permission names."""
    missing: list[str] = []
    try:
        from ApplicationServices import AXIsProcessTrusted
        if not AXIsProcessTrusted():
            missing.append("Accessibility")
    except ImportError:
        pass
    return missing
