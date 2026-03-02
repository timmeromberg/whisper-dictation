"""Platform abstraction layer for macOS / Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PLATFORM = sys.platform


def data_dir() -> Path:
    """Platform-appropriate data directory for whisper-dic."""
    if _PLATFORM == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "whisper-dic"

if _PLATFORM == "darwin":
    from ._macos import (  # noqa: F401
        FLAG_ALT,
        FLAG_CMD,
        FLAG_CTRL,
        FLAG_SHIFT,
        MASK_CONTROL,
        MASK_SHIFT,
        PASTE_MODIFIER_KEY,
        TERMINAL_APP_IDS,
        VK_MAP,
        VK_RETURN,
        check_accessibility,
        frontmost_app_id,
        modifier_is_pressed,
        notify,
        play_wav_file,
        post_key,
        post_keycode,
    )
elif _PLATFORM == "win32":
    from ._windows import (  # noqa: F401
        FLAG_ALT,
        FLAG_CMD,
        FLAG_CTRL,
        FLAG_SHIFT,
        MASK_CONTROL,
        MASK_SHIFT,
        PASTE_MODIFIER_KEY,
        TERMINAL_APP_IDS,
        VK_MAP,
        VK_RETURN,
        check_accessibility,
        frontmost_app_id,
        modifier_is_pressed,
        notify,
        play_wav_file,
        post_key,
        post_keycode,
    )
elif _PLATFORM.startswith("linux"):
    from ._linux import (  # noqa: F401
        FLAG_ALT,
        FLAG_CMD,
        FLAG_CTRL,
        FLAG_SHIFT,
        MASK_CONTROL,
        MASK_SHIFT,
        PASTE_MODIFIER_KEY,
        TERMINAL_APP_IDS,
        VK_MAP,
        VK_RETURN,
        check_accessibility,
        frontmost_app_id,
        modifier_is_pressed,
        notify,
        play_wav_file,
        post_key,
        post_keycode,
    )
else:
    raise RuntimeError(f"Unsupported platform: {_PLATFORM}")
