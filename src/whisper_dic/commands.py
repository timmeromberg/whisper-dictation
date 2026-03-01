"""Voice commands — spoken phrases that trigger keyboard shortcuts."""

from __future__ import annotations

import time

from .compat import FLAG_ALT, FLAG_CMD, FLAG_CTRL, FLAG_SHIFT, VK_RETURN
from .compat import VK_MAP as _VK
from .compat import post_key as _post_key
from .log import log

__all__ = ["VK_RETURN", "execute", "list_commands", "register_custom"]

# Command table: normalized spoken phrase -> (virtual_key, modifier_flags)
_COMMANDS: dict[str, tuple[int, int]] = {
    "select all": (_VK["a"], FLAG_CMD),
    "undo": (_VK["z"], FLAG_CMD),
    "undo that": (_VK["z"], FLAG_CMD),
    "redo": (_VK["z"], FLAG_CMD | FLAG_SHIFT),
    "copy": (_VK["c"], FLAG_CMD),
    "copy text": (_VK["c"], FLAG_CMD),
    "copy that": (_VK["c"], FLAG_CMD),
    "copy it": (_VK["c"], FLAG_CMD),
    "copy this": (_VK["c"], FLAG_CMD),
    "cut": (_VK["x"], FLAG_CMD),
    "cut text": (_VK["x"], FLAG_CMD),
    "cut that": (_VK["x"], FLAG_CMD),
    "cut it": (_VK["x"], FLAG_CMD),
    "paste": (_VK["v"], FLAG_CMD),
    "paste text": (_VK["v"], FLAG_CMD),
    "paste that": (_VK["v"], FLAG_CMD),
    "paste it": (_VK["v"], FLAG_CMD),
    "paste this": (_VK["v"], FLAG_CMD),
    "save": (_VK["s"], FLAG_CMD),
    "save file": (_VK["s"], FLAG_CMD),
    "save it": (_VK["s"], FLAG_CMD),
    "find": (_VK["f"], FLAG_CMD),
    "new tab": (_VK["t"], FLAG_CMD),
    "close tab": (_VK["w"], FLAG_CMD),
    "delete": (_VK["delete"], 0),
    "delete that": (_VK["delete"], 0),
    "delete it": (_VK["delete"], 0),
    "backspace": (_VK["delete"], 0),
    "enter": (_VK["return"], 0),
    "return": (_VK["return"], 0),
    "tab": (_VK["tab"], 0),
    "escape": (_VK["escape"], 0),
}

_COMMANDS["close window"] = (_VK["w"], FLAG_CMD)
_COMMANDS["new window"] = (_VK["n"], FLAG_CMD)
_COMMANDS["print"] = (_VK["p"], FLAG_CMD)
_COMMANDS["bold"] = (_VK["b"], FLAG_CMD)

# Screenshot to clipboard: Cmd+Ctrl+Shift+4 (area select)
_FLAG_SCREENSHOT = FLAG_CMD | FLAG_SHIFT | FLAG_CTRL
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


_MODIFIER_MAP = {
    "cmd": FLAG_CMD, "command": FLAG_CMD,
    "ctrl": FLAG_CTRL, "control": FLAG_CTRL,
    "shift": FLAG_SHIFT,
    "alt": FLAG_ALT, "option": FLAG_ALT,
}


def _parse_shortcut(shortcut: str) -> tuple[int, int]:
    """Parse a shortcut string like 'cmd+shift+z' into (vk, flags)."""
    parts = [p.strip().lower() for p in shortcut.split("+")]
    if not parts:
        raise ValueError(f"Empty shortcut: {shortcut!r}")

    key_name = parts[-1]
    if key_name not in _VK:
        raise ValueError(f"Unknown key {key_name!r}. Available: {', '.join(sorted(_VK))}")

    flags = 0
    for mod in parts[:-1]:
        if mod not in _MODIFIER_MAP:
            raise ValueError(f"Unknown modifier {mod!r}. Available: {', '.join(sorted(_MODIFIER_MAP))}")
        flags |= _MODIFIER_MAP[mod]

    return _VK[key_name], flags


def register_custom(custom_commands: dict[str, str]) -> None:
    """Register custom voice commands from config."""
    for phrase, shortcut in custom_commands.items():
        try:
            vk, flags = _parse_shortcut(shortcut)
            normalized = phrase.strip().lower()
            _COMMANDS[normalized] = (vk, flags)
            log("command", f"Registered custom: '{normalized}' -> {shortcut}")
        except ValueError as exc:
            log("command", f"Invalid custom command '{phrase}': {exc}")
