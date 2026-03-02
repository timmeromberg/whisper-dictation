"""Tests for TextPaster."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestFrontmostAppId:
    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only compat path")
    def test_returns_app_id(self) -> None:
        with patch("whisper_dic.compat._macos.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="com.apple.Terminal\n")
            from whisper_dic.paster import frontmost_app_id
            assert frontmost_app_id() == "com.apple.Terminal"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only compat path")
    def test_returns_empty_on_error(self) -> None:
        with patch("whisper_dic.compat._macos.subprocess.run", side_effect=Exception("fail")):
            from whisper_dic.paster import frontmost_app_id
            assert frontmost_app_id() == ""


class TestTextPaster:
    @pytest.fixture(autouse=True)
    def _mock_keyboard_controller(self):
        # Prevent real key injection (Cmd/Ctrl+V) during tests.
        with patch("whisper_dic.paster.Controller", return_value=MagicMock()):
            yield

    def test_paste_empty_does_nothing(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster()
        with patch("whisper_dic.paster.pyperclip") as mock_clip:
            p.paste("")
            mock_clip.copy.assert_not_called()

    def test_paste_whitespace_does_nothing(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster()
        with patch("whisper_dic.paster.pyperclip") as mock_clip:
            p.paste("   ")
            mock_clip.copy.assert_not_called()

    def test_paste_copies_to_clipboard_and_restores(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster(pre_paste_delay=0, clipboard_restore_delay=0)
        with patch("whisper_dic.paster.pyperclip") as mock_clip, patch("whisper_dic.paster.time"):
            mock_clip.paste.side_effect = ["old clipboard", "hello world"]
            p.paste("hello world")
            # First call sets dictated text, second restores previous clipboard
            assert mock_clip.copy.call_count == 2
            mock_clip.copy.assert_any_call("hello world")
            mock_clip.copy.assert_any_call("old clipboard")

    def test_paste_skips_restore_when_clipboard_changed(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster(pre_paste_delay=0, clipboard_restore_delay=0)
        with patch("whisper_dic.paster.pyperclip") as mock_clip, patch("whisper_dic.paster.time"):
            mock_clip.paste.side_effect = ["old clipboard", "new clipboard value"]
            p.paste("hello world")
            assert mock_clip.copy.call_count == 1
            mock_clip.copy.assert_called_once_with("hello world")

    def test_auto_send_in_terminal(self) -> None:
        from whisper_dic.compat import TERMINAL_APP_IDS
        from whisper_dic.paster import TextPaster
        # Pick the first terminal app ID for whatever platform we're on
        terminal_id = next(iter(TERMINAL_APP_IDS))
        p = TextPaster(pre_paste_delay=0, clipboard_restore_delay=0)
        with (
            patch("whisper_dic.paster.pyperclip"),
            patch("whisper_dic.paster.time"),
            patch("whisper_dic.paster.frontmost_app_id", return_value=terminal_id),
            patch("whisper_dic.paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_post.assert_called_once()

    def test_auto_send_skips_non_terminal(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster(pre_paste_delay=0, clipboard_restore_delay=0)
        with (
            patch("whisper_dic.paster.pyperclip"),
            patch("whisper_dic.paster.time"),
            patch("whisper_dic.paster.frontmost_app_id", return_value="com.example.NotATerminal"),
            patch("whisper_dic.paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_post.assert_not_called()

    def test_smoke_mode_skips_all_side_effects(self) -> None:
        from whisper_dic.paster import TextPaster
        p = TextPaster(pre_paste_delay=0, clipboard_restore_delay=0)
        with (
            patch.dict("os.environ", {"WHISPER_DIC_SMOKE_NO_INPUT": "1"}, clear=False),
            patch("whisper_dic.paster.pyperclip") as mock_clip,
            patch("whisper_dic.paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_clip.copy.assert_not_called()
            mock_post.assert_not_called()
