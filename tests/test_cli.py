"""Tests for CLI argument parsing."""

from __future__ import annotations

from whisper_dic.cli import build_parser


class TestBuildParser:
    def test_default_command_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_run_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["run"])
        assert args.command == "run"

    def test_status_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_set_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["set", "whisper.language", "nl"])
        assert args.command == "set"
        assert args.key == "whisper.language"
        assert args.value == "nl"

    def test_provider_no_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["provider"])
        assert args.command == "provider"
        assert args.provider is None

    def test_provider_with_arg(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["provider", "groq"])
        assert args.provider == "groq"

    def test_custom_config_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["status", "--config", "/tmp/test.toml"])
        assert args.config == "/tmp/test.toml"

    def test_version_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["version"])
        assert args.command == "version"

    def test_logs_default_lines(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["logs"])
        assert args.lines == "50"

    def test_logs_custom_lines(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["logs", "-n", "100"])
        assert args.lines == "100"

    def test_menubar_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["menubar"])
        assert args.command == "menubar"

    def test_install_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["install"])
        assert args.command == "install"

    def test_uninstall_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["uninstall"])
        assert args.command == "uninstall"

    def test_discover_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["discover"])
        assert args.command == "discover"
