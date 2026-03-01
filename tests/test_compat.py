"""Tests for the compat layer contract — runs on all platforms."""

from __future__ import annotations

import compat


class TestExportsExist:
    """Every platform backend must export these symbols."""

    def test_flag_constants(self) -> None:
        assert hasattr(compat, "FLAG_CMD")
        assert hasattr(compat, "FLAG_CTRL")
        assert hasattr(compat, "FLAG_SHIFT")
        assert hasattr(compat, "FLAG_ALT")

    def test_mask_constants(self) -> None:
        assert hasattr(compat, "MASK_CONTROL")
        assert hasattr(compat, "MASK_SHIFT")

    def test_vk_map(self) -> None:
        assert hasattr(compat, "VK_MAP")
        assert hasattr(compat, "VK_RETURN")

    def test_functions(self) -> None:
        assert callable(compat.post_key)
        assert callable(compat.post_keycode)
        assert callable(compat.modifier_is_pressed)
        assert callable(compat.frontmost_app_id)
        assert callable(compat.notify)
        assert callable(compat.play_wav_file)
        assert callable(compat.check_accessibility)

    def test_paste_modifier_key(self) -> None:
        assert hasattr(compat, "PASTE_MODIFIER_KEY")

    def test_terminal_app_ids(self) -> None:
        assert hasattr(compat, "TERMINAL_APP_IDS")
        assert isinstance(compat.TERMINAL_APP_IDS, set)
        assert len(compat.TERMINAL_APP_IDS) > 0


class TestFlagConstants:
    """Flags must be non-zero and usable as bitmask components."""

    def test_cmd_nonzero(self) -> None:
        assert compat.FLAG_CMD != 0

    def test_ctrl_nonzero(self) -> None:
        assert compat.FLAG_CTRL != 0

    def test_shift_nonzero(self) -> None:
        assert compat.FLAG_SHIFT != 0

    def test_alt_nonzero(self) -> None:
        assert compat.FLAG_ALT != 0

    def test_shift_differs_from_ctrl(self) -> None:
        assert compat.FLAG_SHIFT != compat.FLAG_CTRL


class TestVKMap:
    """VK_MAP must contain all keys used by commands and shortcuts."""

    REQUIRED_KEYS = [
        # Letters
        "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
        "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
        # Digits
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        # Special keys
        "return", "tab", "escape", "delete", "space",
        # Arrow keys
        "up", "down", "left", "right",
        # Punctuation (for custom commands)
        "-", "=",
    ]

    def test_all_required_keys_present(self) -> None:
        for key in self.REQUIRED_KEYS:
            assert key in compat.VK_MAP, f"VK_MAP missing key '{key}'"

    def test_values_are_integers(self) -> None:
        for key, vk in compat.VK_MAP.items():
            assert isinstance(vk, int), f"VK_MAP['{key}'] = {vk!r} is not int"

    def test_vk_return_matches_map(self) -> None:
        assert compat.VK_RETURN == compat.VK_MAP["return"]
