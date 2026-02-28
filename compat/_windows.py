"""Windows platform implementations (ctypes + Win32 API)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import time
import winsound

from pynput.keyboard import Key

from log import log

user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# SendInput structs
# ---------------------------------------------------------------------------

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    _anonymous_ = ("_union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_union", _INPUT_UNION),
    ]


def _send_input(vk: int, up: bool = False) -> None:
    flags = KEYEVENTF_KEYUP if up else 0
    inp = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None),
    )
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# Modifier checking
# ---------------------------------------------------------------------------

# Windows virtual-key codes for modifiers
_VK_CONTROL = 0x11
_VK_SHIFT = 0x10
_VK_MENU = 0x12  # Alt

# Mask constants (used by hotkey.py) — map to VK codes for GetAsyncKeyState
MASK_CONTROL = _VK_CONTROL
MASK_SHIFT = _VK_SHIFT


def modifier_is_pressed(mask: int) -> bool:
    """Check if a modifier key is physically held (via GetAsyncKeyState)."""
    return bool(user32.GetAsyncKeyState(mask) & 0x8000)


# ---------------------------------------------------------------------------
# Key simulation
# ---------------------------------------------------------------------------

# Windows virtual key codes
VK_RETURN = 0x0D

VK_MAP = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46, "g": 0x47,
    "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E,
    "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54, "u": 0x55,
    "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
    "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "return": 0x0D, "tab": 0x09, "escape": 0x1B, "delete": 0x08,
    "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0,
}

# Modifier flags — bitmask used by commands.py command table.
# On Windows, CMD maps to CTRL (Cmd shortcuts become Ctrl shortcuts).
FLAG_CTRL = 1 << 0
FLAG_CMD = FLAG_CTRL  # no Cmd key on Windows — treat as Ctrl
FLAG_SHIFT = 1 << 1
FLAG_ALT = 1 << 2

_FLAG_TO_VK = {
    FLAG_CTRL: _VK_CONTROL,
    FLAG_SHIFT: _VK_SHIFT,
    FLAG_ALT: _VK_MENU,
}


def post_key(vk: int, flags: int = 0) -> None:
    """Post a key event with optional modifier flags via SendInput."""
    # Press modifier keys
    held: list[int] = []
    for flag, mod_vk in _FLAG_TO_VK.items():
        if flags & flag:
            _send_input(mod_vk, up=False)
            held.append(mod_vk)

    # Press and release the key
    _send_input(vk, up=False)
    time.sleep(0.01)
    _send_input(vk, up=True)

    # Release modifier keys (reverse order)
    for mod_vk in reversed(held):
        _send_input(mod_vk, up=True)


def post_keycode(vk: int) -> None:
    """Post a key down + key up via SendInput (no modifiers)."""
    _send_input(vk, up=False)
    time.sleep(0.01)
    _send_input(vk, up=True)


# ---------------------------------------------------------------------------
# Frontmost app detection
# ---------------------------------------------------------------------------

TERMINAL_APP_IDS: set[str] = {
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "WindowsTerminal.exe",
    "wezterm-gui.exe",
    "alacritty.exe",
    "Code.exe",
    "idea64.exe",
    "pycharm64.exe",
    "webstorm64.exe",
    "clion64.exe",
    "goland64.exe",
    "rider64.exe",
    "rubymine64.exe",
    "phpstorm64.exe",
    "datagrip64.exe",
    "ConEmu64.exe",
    "ConEmuC64.exe",
    "mintty.exe",
    "kitty.exe",
    "hyper.exe",
}

PASTE_MODIFIER_KEY = Key.ctrl

# Process query constants
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def frontmost_app_id() -> str:
    """Get the exe name of the foreground window process."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value,
        )
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            full_path = buf.value
            # Return just the exe name (e.g. "Code.exe")
            return full_path.rsplit("\\", 1)[-1] if full_path else ""
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Notifications & audio
# ---------------------------------------------------------------------------


def notify(message: str, title: str = "whisper-dic") -> None:
    """No-op on Windows MVP — just log."""
    log("notify", f"[{title}] {message}")


def play_wav_file(path: str) -> None:
    """Play a WAV file via Windows winsound (stdlib)."""
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME)
    except Exception as exc:
        log("audio", f"Playback failed: {exc}")


# ---------------------------------------------------------------------------
# Accessibility check
# ---------------------------------------------------------------------------


def check_accessibility() -> list[str]:
    """No accessibility permission check needed on Windows."""
    return []
