"""Linux fallback implementations for CI and basic CLI operation."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pynput.keyboard import Key

from ..log import log

# Keep modifier mask API-compatible with other backends.
MASK_CONTROL = 0x11
MASK_SHIFT = 0x10


def modifier_is_pressed(mask: int) -> bool:
    """Best-effort modifier check on Linux fallback backend."""
    _ = mask
    return False


# Reuse a complete virtual-key map contract for command parsing tests.
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

# Linux has no Cmd key; map command shortcuts to Ctrl behavior.
FLAG_CTRL = 1 << 0
FLAG_CMD = FLAG_CTRL
FLAG_SHIFT = 1 << 1
FLAG_ALT = 1 << 2


def post_key(vk: int, flags: int = 0) -> None:
    """Fallback no-op key posting on Linux."""
    log("compat-linux", f"post_key(vk={vk}, flags={flags}) not implemented on linux backend")


def post_keycode(vk: int) -> None:
    """Fallback no-op keycode posting on Linux."""
    log("compat-linux", f"post_keycode(vk={vk}) not implemented on linux backend")


TERMINAL_APP_IDS: set[str] = {
    "gnome-terminal-server",
    "konsole",
    "kitty",
    "alacritty",
    "wezterm",
    "tilix",
    "xfce4-terminal",
    "code",
}

PASTE_MODIFIER_KEY = Key.ctrl


def _run_capture(args: list[str], timeout: float = 0.4) -> str:
    """Run a command and return stripped stdout, or empty string on failure."""
    try:
        proc = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _pid_from_xdotool() -> int | None:
    """Resolve focused window PID using xdotool when available."""
    if shutil.which("xdotool") is None:
        return None
    out = _run_capture(["xdotool", "getwindowfocus", "getwindowpid"])
    if not out:
        return None
    try:
        pid = int(out)
    except ValueError:
        return None
    return pid if pid > 0 else None


def _pid_from_xprop() -> int | None:
    """Resolve active window PID using xprop (EWMH)."""
    if shutil.which("xprop") is None:
        return None

    root = _run_capture(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    if not root:
        return None

    match = re.search(r"(0x[0-9a-fA-F]+)", root)
    if match is None:
        return None
    window_id = match.group(1)
    if window_id == "0x0":
        return None

    win = _run_capture(["xprop", "-id", window_id, "_NET_WM_PID"])
    if not win:
        return None
    pid_match = re.search(r"=\s*(\d+)", win)
    if pid_match is None:
        return None
    pid = int(pid_match.group(1))
    return pid if pid > 0 else None


def _frontmost_pid() -> int | None:
    """Best-effort frontmost PID resolution for Linux desktops."""
    return _pid_from_xdotool() or _pid_from_xprop()


def _process_name_for_pid(pid: int) -> str:
    """Resolve process name for PID, preferring /proc metadata."""
    comm_path = Path(f"/proc/{pid}/comm")
    try:
        comm = comm_path.read_text(encoding="utf-8").strip()
    except OSError:
        comm = ""
    if comm:
        return comm

    exe_path = Path(f"/proc/{pid}/exe")
    try:
        target = exe_path.resolve(strict=True)
    except OSError:
        target = None
    if target is not None and target.name:
        return target.name

    out = _run_capture(["ps", "-p", str(pid), "-o", "comm="])
    return out.strip()


def frontmost_app_id() -> str:
    """Best-effort frontmost app detection on Linux backend."""
    pid = _frontmost_pid()
    if pid is None:
        return ""
    name = _process_name_for_pid(pid)
    return name.lower() if name else ""


def notify(message: str, title: str = "whisper-dic") -> None:
    """No-op desktop notification fallback for Linux."""
    log("notify", f"[{title}] {message}")


def play_wav_file(path: str) -> None:
    """No-op playback fallback for Linux backend."""
    log("audio", f"Linux fallback playback for {path} is not implemented")


def check_accessibility() -> list[str]:
    """No accessibility permission check for Linux fallback backend."""
    return []
