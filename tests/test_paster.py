"""Tests for TextPaster."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestFrontmostAppId:
    def test_returns_app_id(self) -> None:
        with patch("compat._macos.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="com.apple.Terminal\n")
            from paster import frontmost_app_id
            assert frontmost_app_id() == "com.apple.Terminal"

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

    def test_paste_copies_to_clipboard(self) -> None:
        from paster import TextPaster
        p = TextPaster(paste_delay_seconds=0)
        with patch("paster.pyperclip") as mock_clip, patch("paster.time"):
            p.paste("hello world")
            mock_clip.copy.assert_called_once_with("hello world")

    def test_auto_send_in_terminal(self) -> None:
        from paster import TextPaster
        p = TextPaster(paste_delay_seconds=0)
        with (
            patch("paster.pyperclip"),
            patch("paster.time"),
            patch("paster.frontmost_app_id", return_value="com.apple.Terminal"),
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
            patch("paster.frontmost_app_id", return_value="com.apple.Safari"),
            patch("paster.post_keycode") as mock_post,
        ):
            p.paste("test", auto_send=True)
            mock_post.assert_not_called()
