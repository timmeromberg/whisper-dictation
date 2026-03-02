"""Tests for HotkeyListener."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pynput import keyboard

from whisper_dic.hotkey import KEY_MAP, HotkeyListener


class TestKeyMap:
    def test_expected_keys_present(self) -> None:
        expected = {
            "left_option", "alt_l", "left_alt",
            "right_option", "alt_r", "right_alt",
            "right_command", "right_shift",
            "left_command", "left_shift",
        }
        assert expected == set(KEY_MAP.keys())

    def test_left_option_maps_to_alt_l(self) -> None:
        assert KEY_MAP["left_option"] == keyboard.Key.alt_l

    def test_right_option_maps_to_alt_r(self) -> None:
        assert KEY_MAP["right_option"] == keyboard.Key.alt_r


class TestHotkeyListenerInit:
    def test_valid_key(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        assert listener._key_name == "left_option"

    def test_invalid_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported hotkey"):
            HotkeyListener(
                on_hold_start=lambda: None,
                on_hold_end=lambda a, b: None,
                key_name="nonexistent",
            )


class TestSetKey:
    def test_changes_target(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        listener.set_key("right_option")
        assert listener._key_name == "right_option"

    def test_invalid_raises(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        with pytest.raises(ValueError, match="Unsupported"):
            listener.set_key("invalid_key")


class TestMatches:
    def test_exact_match(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        assert listener._matches(keyboard.Key.alt_l) is True

    def test_no_match(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        assert listener._matches(keyboard.Key.shift) is False

    def test_none_key(self) -> None:
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda a, b: None,
            key_name="left_option",
        )
        assert listener._matches(None) is False


class TestReleaseDebounce:
    def test_debounced_release_passes_hold_duration(self) -> None:
        calls: list[tuple[bool, bool, float | None]] = []
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda auto_send, command_mode, hold_duration: calls.append(
                (auto_send, command_mode, hold_duration),
            ),
            key_name="left_option",
        )
        listener._release_seq = 1

        with patch("whisper_dic.hotkey.time.sleep", return_value=None):
            listener._debounced_release(1, True, False, 0.05)

        assert calls == [(True, False, 0.05)]
        assert listener._pressed is False

    def test_debounced_release_ignores_stale_sequence(self) -> None:
        calls: list[tuple[bool, bool, float | None]] = []
        listener = HotkeyListener(
            on_hold_start=lambda: None,
            on_hold_end=lambda auto_send, command_mode, hold_duration: calls.append(
                (auto_send, command_mode, hold_duration),
            ),
            key_name="left_option",
        )
        listener._release_seq = 2

        with patch("whisper_dic.hotkey.time.sleep", return_value=None):
            listener._debounced_release(1, False, True, 0.1)

        assert calls == []
