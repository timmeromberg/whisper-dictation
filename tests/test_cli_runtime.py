"""Runtime behavior tests for CLI helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from whisper_dic.cli import (
    _ALLOW_PY314_ENV,
    _load_config_from_path,
    _pid_file_path,
    _runtime_supported,
    _state_dir,
    command_set,
    command_setup,
)


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

    def test_runtime_supported_blocks_py314_macos_menubar(self) -> None:
        with (
            patch("whisper_dic.cli.sys.platform", "darwin"),
            patch("whisper_dic.cli.sys.version_info", (3, 14, 0)),
            patch.dict("whisper_dic.cli.os.environ", {}, clear=False),
        ):
            assert _runtime_supported("menubar") is False

    def test_runtime_supported_allows_py314_with_override(self) -> None:
        with (
            patch("whisper_dic.cli.sys.platform", "darwin"),
            patch("whisper_dic.cli.sys.version_info", (3, 14, 0)),
            patch.dict("whisper_dic.cli.os.environ", {_ALLOW_PY314_ENV: "1"}, clear=False),
        ):
            assert _runtime_supported("menubar") is True

    def test_runtime_supported_allows_non_interactive_commands(self) -> None:
        with (
            patch("whisper_dic.cli.sys.platform", "darwin"),
            patch("whisper_dic.cli.sys.version_info", (3, 14, 0)),
        ):
            assert _runtime_supported("status") is True

    @pytest.mark.skipif(os.name == "nt", reason="POSIX chmod semantics")
    def test_load_config_tightens_non_owner_permissions(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('[hotkey]\nkey = "left_option"\n', encoding="utf-8")
        cfg.chmod(0o664)
        _load_config_from_path(cfg)
        mode = cfg.stat().st_mode & 0o777
        assert mode == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="POSIX /tmp fallback only")
    def test_state_dir_fallback_in_tmp_is_private(self, tmp_path: Path) -> None:
        broken_state_home = tmp_path / "not-a-directory"
        broken_state_home.write_text("x", encoding="utf-8")

        uid = os.getuid()
        fallback = Path(tempfile.gettempdir()) / f"whisper-dic-{uid}"
        with (
            patch("whisper_dic.cli.sys.platform", "linux"),
            patch("whisper_dic.cli.os.getuid", return_value=uid),
            patch.dict("whisper_dic.cli.os.environ", {"XDG_STATE_HOME": str(broken_state_home)}, clear=False),
        ):
            got = _state_dir()
        assert got == fallback
        st = got.stat()
        mode = st.st_mode & 0o777
        assert st.st_uid == uid
        assert mode == 0o700

    @pytest.mark.skipif(os.name == "nt", reason="POSIX /tmp fallback only")
    def test_state_dir_fallback_rejects_non_directory(self, tmp_path: Path) -> None:
        broken_state_home = tmp_path / "not-a-directory"
        broken_state_home.write_text("x", encoding="utf-8")

        uid = 987655
        fallback = Path(tempfile.gettempdir()) / f"whisper-dic-{uid}"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text("not a dir", encoding="utf-8")
        try:
            with (
                patch("whisper_dic.cli.sys.platform", "linux"),
                patch("whisper_dic.cli.os.getuid", return_value=uid),
                patch.dict("whisper_dic.cli.os.environ", {"XDG_STATE_HOME": str(broken_state_home)}, clear=False),
            ):
                with pytest.raises(OSError):
                    _state_dir()
        finally:
            fallback.unlink(missing_ok=True)
