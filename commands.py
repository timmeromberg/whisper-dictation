"""Voice commands — spoken phrases that trigger keyboard shortcuts."""

from __future__ import annotations

import time

import Quartz

# macOS virtual key codes
_VK = {
    "a": 0, "b": 11, "c": 8, "d": 2, "f": 3, "n": 45, "p": 35,
    "s": 1, "v": 9, "x": 7, "z": 6,
    "return": 36, "tab": 48, "escape": 53, "delete": 51,
    "space": 49, "up": 126, "down": 125, "left": 123, "right": 124,
}

_FLAG_CMD = Quartz.kCGEventFlagMaskCommand
_FLAG_SHIFT = Quartz.kCGEventFlagMaskShift
_FLAG_ALT = Quartz.kCGEventFlagMaskAlternate

# Command table: normalized spoken phrase -> (virtual_key, modifier_flags)
_COMMANDS: dict[str, tuple[int, int]] = {
    "select all": (_VK["a"], _FLAG_CMD),
    "undo": (_VK["z"], _FLAG_CMD),
    "redo": (_VK["z"], _FLAG_CMD | _FLAG_SHIFT),
    "copy": (_VK["c"], _FLAG_CMD),
    "cut": (_VK["x"], _FLAG_CMD),
    "paste": (_VK["v"], _FLAG_CMD),
    "save": (_VK["s"], _FLAG_CMD),
    "find": (_VK["f"], _FLAG_CMD),
    "new tab": (_VK["tab"], _FLAG_CMD),
    "close tab": (_VK["x"], _FLAG_CMD),  # Cmd+W would be better but no 'w' in _VK
    "delete": (_VK["delete"], 0),
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

# Aliases for common Whisper mishearings
_ALIASES: dict[str, str] = {
    "peace": "paste",
    "paced": "paste",
    "based": "paste",
    "face": "paste",
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
    normalized = _ALIASES.get(normalized, normalized)
    entry = _COMMANDS.get(normalized)
    if entry is None:
        return False

    vk, flags = entry
    time.sleep(0.05)
    _post_key(vk, flags)
    print(f"[command] Executed: '{normalized}'")
    return True


def list_commands() -> list[str]:
    """Return sorted list of available command names."""
    return sorted(_COMMANDS.keys())