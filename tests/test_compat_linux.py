"""Tests for Linux compatibility helpers."""

from __future__ import annotations

from unittest.mock import patch

from whisper_dic.compat import _linux


def test_frontmost_app_id_from_xdotool_path() -> None:
    with (
        patch("whisper_dic.compat._linux._pid_from_xdotool", return_value=1234),
        patch("whisper_dic.compat._linux._process_name_for_pid", return_value="Code"),
    ):
        assert _linux.frontmost_app_id() == "code"


def test_frontmost_app_id_falls_back_to_xprop() -> None:
    with (
        patch("whisper_dic.compat._linux._pid_from_xdotool", return_value=None),
        patch("whisper_dic.compat._linux._pid_from_xprop", return_value=987),
    ):
        assert _linux._frontmost_pid() == 987


def test_frontmost_app_id_returns_empty_when_no_pid() -> None:
    with patch("whisper_dic.compat._linux._frontmost_pid", return_value=None):
        assert _linux.frontmost_app_id() == ""


def test_pid_from_xprop_parses_active_window_pid() -> None:
    def _fake_run(args: list[str], timeout: float = 0.4) -> str:
        _ = timeout
        if args[:2] == ["xprop", "-root"]:
            return "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x3e00007"
        if args[:2] == ["xprop", "-id"]:
            return "_NET_WM_PID(CARDINAL) = 4242"
        return ""

    with (
        patch("whisper_dic.compat._linux.shutil.which", return_value="/usr/bin/xprop"),
        patch("whisper_dic.compat._linux._run_capture", side_effect=_fake_run),
    ):
        assert _linux._pid_from_xprop() == 4242
