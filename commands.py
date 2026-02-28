"""Voice commands — spoken phrases that trigger keyboard shortcuts."""

from __future__ import annotations

import time

import Quartz

from log import log

# macOS virtual key codes
VK_RETURN = 36

_VK = {
    "a": 0, "b": 11, "c": 8, "d": 2, "f": 3, "n": 45, "p": 35,
    "s": 1, "v": 9, "x": 7, "z": 6,
    "return": 36, "tab": 48, "escape": 53, "delete": 51,
    "space": 49, "up": 126, "down": 125, "left": 123, "right": 124,
    "3": 20, "4": 21,
}

_FLAG_CMD = Quartz.kCGEventFlagMaskCommand
_FLAG_SHIFT = Quartz.kCGEventFlagMaskShift
_FLAG_ALT = Quartz.kCGEventFlagMaskAlternate

# Command table: normalized spoken phrase -> (virtual_key, modifier_flags)
_COMMANDS: dict[str, tuple[int, int]] = {
    "select all": (_VK["a"], _FLAG_CMD),
    "undo": (_VK["z"], _FLAG_CMD),
    "undo that": (_VK["z"], _FLAG_CMD),
    "redo": (_VK["z"], _FLAG_CMD | _FLAG_SHIFT),
    "copy": (_VK["c"], _FLAG_CMD),
    "copy text": (_VK["c"], _FLAG_CMD),
    "copy that": (_VK["c"], _FLAG_CMD),
    "copy it": (_VK["c"], _FLAG_CMD),
    "copy this": (_VK["c"], _FLAG_CMD),
    "cut": (_VK["x"], _FLAG_CMD),
    "cut text": (_VK["x"], _FLAG_CMD),
    "cut that": (_VK["x"], _FLAG_CMD),
    "cut it": (_VK["x"], _FLAG_CMD),
    "paste": (_VK["v"], _FLAG_CMD),
    "paste text": (_VK["v"], _FLAG_CMD),
    "paste that": (_VK["v"], _FLAG_CMD),
    "paste it": (_VK["v"], _FLAG_CMD),
    "paste this": (_VK["v"], _FLAG_CMD),
    "save": (_VK["s"], _FLAG_CMD),
    "save file": (_VK["s"], _FLAG_CMD),
    "save it": (_VK["s"], _FLAG_CMD),
    "find": (_VK["f"], _FLAG_CMD),
    "new tab": (_VK["tab"], _FLAG_CMD),
    "close tab": (_VK["x"], _FLAG_CMD),  # Cmd+W would be better but no 'w' in _VK
    "delete": (_VK["delete"], 0),
    "delete that": (_VK["delete"], 0),
    "delete it": (_VK["delete"], 0),
    "backspace": (_VK["delete"], 0),
    "enter": (_VK["return"], 0),
    "return": (_VK["return"], 0),
    "tab": (_VK["tab"], 0),
    "escape": (_VK["escape"], 0),
}

# Add missing key codes
_VK["w"] = 13
_COMMANDS["close tab"] = (_VK["w"], _FLAG_CMD)
_COMMANDS["close window"] = (_VK["w"], _FLAG_CMD)
_COMMANDS["new window"] = (_VK["n"], _FLAG_CMD)
_COMMANDS["print"] = (_VK["p"], _FLAG_CMD)
_COMMANDS["bold"] = (_VK["b"], _FLAG_CMD)

# Screenshot to clipboard: Cmd+Ctrl+Shift+4 (area select)
_FLAG_SCREENSHOT = _FLAG_CMD | _FLAG_SHIFT | Quartz.kCGEventFlagMaskControl
_COMMANDS["screenshot"] = (_VK["4"], _FLAG_SCREENSHOT)
_COMMANDS["take screenshot"] = (_VK["4"], _FLAG_SCREENSHOT)
_COMMANDS["take a screenshot"] = (_VK["4"], _FLAG_SCREENSHOT)
_COMMANDS["screen capture"] = (_VK["4"], _FLAG_SCREENSHOT)
_COMMANDS["capture screen"] = (_VK["4"], _FLAG_SCREENSHOT)
# Full screen to clipboard: Cmd+Ctrl+Shift+3
_COMMANDS["full screenshot"] = (_VK["3"], _FLAG_SCREENSHOT)
_COMMANDS["screenshot full"] = (_VK["3"], _FLAG_SCREENSHOT)
_COMMANDS["screenshot full screen"] = (_VK["3"], _FLAG_SCREENSHOT)

# Aliases for common Whisper mishearings
_ALIASES: dict[str, str] = {
    "peace": "paste",
    "paced": "paste",
    "based": "paste",
    "face": "paste",
    "peace text": "paste text",
    "paced text": "paste text",
    "paste decks": "paste text",
    "paste next": "paste text",
    "tub": "tab",
    "tap": "tab",
    "on do": "undo",
    "and do": "undo",
    "safe": "save",
    "say": "save",
    "copie": "copy",
    "coffee": "copy",
    "caught": "cut",
    "cup": "cut",
    "escaped": "escape",
    "deletes": "delete",
    "read do": "redo",
    "redo it": "redo",
}


def _post_key(vk: int, flags: int = 0) -> None:
    """Post a key event with optional modifier flags via CGEvent."""
    down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
    if flags:
        Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def execute(text: str) -> bool:
    """Try to match text to a voice command and execute it.

    Returns True if a command was executed, False if no match.
    """
    normalized = text.strip().lower()
    # Strip trailing punctuation that Whisper might add
    normalized = normalized.rstrip(".!?,;:")

    # Check aliases first, then direct match
    original = normalized
    normalized = _ALIASES.get(normalized, normalized)
    if original != normalized:
        log("command", f"Alias: '{original}' -> '{normalized}'")

    entry = _COMMANDS.get(normalized)
    if entry is None:
        log("command", f"No match for '{normalized}'")
        return False

    vk, flags = entry
    log("command", f"Executing: '{normalized}' (vk={vk}, flags=0x{flags:x})")
    time.sleep(0.05)
    _post_key(vk, flags)
    log("command", f"Done: '{normalized}'")
    return True


def list_commands() -> list[str]:
    """Return sorted list of available command names."""
    return sorted(_COMMANDS.keys())