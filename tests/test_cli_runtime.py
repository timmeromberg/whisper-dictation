"""Runtime behavior tests for CLI helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from whisper_dic.cli import _load_config_from_path, _pid_file_path, command_set, command_setup


class TestCommandSet:
    def test_redacts_secret_values(self, capsys) -> None:
        with (
            patch("whisper_dic.cli._load_config_from_path"),
            patch("whisper_dic.cli.set_config_value"),
        ):
            rc = command_set(Path("/tmp/config.toml"), "whisper.groq.api_key", "gsk_super_secret")
        assert rc == 0
        out = capsys.readouterr().out
        assert "whisper.groq.api_key" in out
        assert '"***"' in out
        assert "gsk_super_secret" not in out

    def test_keeps_non_secret_values(self, capsys) -> None:
        with (
            patch("whisper_dic.cli._load_config_from_path"),
            patch("whisper_dic.cli.set_config_value"),
        ):
            rc = command_set(Path("/tmp/config.toml"), "whisper.language", "nl")
        assert rc == 0
        out = capsys.readouterr().out
        assert '[config] Set whisper.language = "nl"' in out


class TestCliRuntime:
    def test_pid_file_path_uses_state_dir(self) -> None:
        with patch("whisper_dic.cli._state_dir", return_value=Path("/tmp/custom-state")):
            assert _pid_file_path() == Path("/tmp/custom-state/whisper-dic.pid")

    def test_setup_non_macos_is_guarded(self, capsys) -> None:
        with patch("whisper_dic.cli.sys.platform", "win32"):
            rc = command_setup(Path("/tmp/config.toml"))
        assert rc == 1
        out = capsys.readouterr().out
        assert "macOS only" in out

    @pytest.mark.skipif(os.name == "nt", reason="POSIX chmod semantics")
    def test_load_config_tightens_non_owner_permissions(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[hotkey]\nkey = "left_option"\n', encoding="utf-8")
        cfg.chmod(0o664)
        _load_config_from_path(cfg)
        mode = cfg.stat().st_mode & 0o777
        assert mode == 0o600
