"""Tests for log module."""

from __future__ import annotations

from whisper_dic.log import log


class TestLog:
    def test_outputs_tag_and_message(self, capsys) -> None:
        log("test", "hello world")
        captured = capsys.readouterr()
        assert "[test] hello world" in captured.out

    def test_has_timestamp(self, capsys) -> None:
        log("tag", "msg")
        captured = capsys.readouterr()
        # Format: [HH:MM:SS.mmm][tag] msg
        assert "][tag]" in captured.out
        assert captured.out.startswith("[")
