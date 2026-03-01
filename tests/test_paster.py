"""Tests for TextPaster."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestFrontmostAppId:
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only compat path")
    def test_returns_app_id(self) -> None:
        with patch("compat._macos.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="com.apple.Terminal\n")
            from paster import frontmost_app_id
            assert frontmost_app_id() == "com.apple.Terminal"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only compat path")
    def test_returns_empty_on_error(self) -> None:
        with patch("compat._macos.subprocess.run", side_effect=Exception("fail")):
            from paster import frontmost_app_id
            assert frontmost_app_id() == ""


class TestTextPaster:
    def test_paste_empty_does_nothing(self) -> None:
        from paster import TextPaster
        p = TextPaster()
        with patch("paster.pyperclip") as mock_clip:
            p.paste("")
            mock_clip.copy.assert_not_called()

    def test_paste_whitespace_does_nothing(self) -> None:
        from paster import TextPaster
        p = TextPaster()
        with patch("paster.pyperclip") as mock_clip:
            p.paste("   ")
            mock_clip.copy.assert_not_called()

    def test_paste_copies_to_clipboard_and_restores(self) -> None:
        from paster import TextPaster
        p = TextPaster(paste_delay_seconds=0)
        with patch("paster.pyperclip") as mock_clip, patch("paster.time"):
            mock_clip.paste.return_value = "old clipboard"
            p.paste("hello world")
            # First call sets dictated text, second restores previous clipboard
            assert mock_clip.copy.call_count == 2
            mock_clip.copy.assert_any_call("hello world")
            mock_clip.copy.assert_any_call("old clipboard")

    def test_auto_send_in_terminal(self) -> None:
        from compat import TERMINAL_APP_IDS
        from paster import TextPaster
        # Pick the first terminal app ID for whatever platform we're on
        terminal_id = next(iter(TERMINAL_APP_IDS))
        p = TextPaster(paste_delay_seconds=0)
        with (
            patch("paster.pyperclip"),
            patch("paster.time"),
            patch("paster.frontmost_app_id", return_value=terminal_id),
            patch("paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_post.assert_called_once()

    def test_auto_send_skips_non_terminal(self) -> None:
        from paster import TextPaster
        p = TextPaster(paste_delay_seconds=0)
        with (
            patch("paster.pyperclip"),
            patch("paster.time"),
            patch("paster.frontmost_app_id", return_value="com.example.NotATerminal"),
            patch("paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_post.assert_not_called()
