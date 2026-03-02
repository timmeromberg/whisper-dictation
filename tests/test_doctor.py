"""Tests for doctor diagnostic checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from whisper_dic.config import AppConfig
from whisper_dic.doctor import (
    CheckResult,
    check_accessibility,
    check_config,
    check_groq_api_key,
    check_local_install,
    check_microphone,
    check_provider,
    run_doctor,
)

# ---------------------------------------------------------------------------
# check_config
# ---------------------------------------------------------------------------


class TestCheckConfig:
    def test_missing_config(self, tmp_path: Path) -> None:
        result, config = check_config(tmp_path / "nonexistent.toml")
        assert result.passed is False
        assert "Not found" in result.message
        assert config is None

    def test_valid_config(self, tmp_config: Path) -> None:
        result, config = check_config(tmp_config)
        assert result.passed is True
        assert str(tmp_config) in result.message
        assert isinstance(config, AppConfig)

    def test_invalid_toml(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.toml"
        p.write_text("[invalid\nkey = ")
        result, config = check_config(p)
        assert result.passed is False
        assert "Parse error" in result.message
        assert config is None

    def test_result_name(self, tmp_config: Path) -> None:
        result, _ = check_config(tmp_config)
        assert result.name == "Config file"

    def test_fix_message_on_missing(self, tmp_path: Path) -> None:
        result, _ = check_config(tmp_path / "gone.toml")
        assert "whisper-dic setup" in result.fix


# ---------------------------------------------------------------------------
# check_provider
# ---------------------------------------------------------------------------


class TestCheckProvider:
    def _make_config(self, provider: str = "local") -> AppConfig:
        """Build a minimal AppConfig with the given provider."""
        from whisper_dic.config import (
            AudioFeedbackConfig,
            HotkeyConfig,
            PasteConfig,
            RecordingConfig,
            TextCommandsConfig,
            WhisperConfig,
            WhisperGroqConfig,
            WhisperLocalConfig,
        )

        return AppConfig(
            hotkey=HotkeyConfig(),
            recording=RecordingConfig(),
            paste=PasteConfig(),
            text_commands=TextCommandsConfig(),
            audio_feedback=AudioFeedbackConfig(),
            whisper=WhisperConfig(
                provider=provider,
                local=WhisperLocalConfig(url="http://localhost:2022/v1/audio/transcriptions"),
                groq=WhisperGroqConfig(
                    api_key="gsk_test1234567890",
                    url="https://api.groq.com/openai/v1/audio/transcriptions",
                ),
            ),
        )

    @patch("whisper_dic.doctor.create_transcriber")
    def test_provider_reachable_local(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.return_value = True
        mock_create.return_value = mock_t

        config = self._make_config("local")
        result = check_provider(config)

        assert result.passed is True
        assert "local" in result.name
        assert "localhost:2022" in result.message
        mock_t.close.assert_called_once()

    @patch("whisper_dic.doctor.create_transcriber")
    def test_provider_reachable_groq(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.return_value = True
        mock_create.return_value = mock_t

        config = self._make_config("groq")
        result = check_provider(config)

        assert result.passed is True
        assert "groq" in result.name
        assert "groq.com" in result.message

    @patch("whisper_dic.doctor.create_transcriber")
    def test_provider_unreachable_local(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.return_value = False
        mock_create.return_value = mock_t

        config = self._make_config("local")
        result = check_provider(config)

        assert result.passed is False
        assert "Not reachable" in result.message
        assert "whisper-dic setup-local" in result.fix

    @patch("whisper_dic.doctor.create_transcriber")
    def test_provider_unreachable_groq(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.return_value = False
        mock_create.return_value = mock_t

        config = self._make_config("groq")
        result = check_provider(config)

        assert result.passed is False
        assert "Not reachable" in result.message
        assert "API key" in result.fix

    @patch("whisper_dic.doctor.create_transcriber")
    def test_provider_health_check_exception(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.side_effect = ConnectionError("refused")
        mock_create.return_value = mock_t

        config = self._make_config("local")
        result = check_provider(config)

        assert result.passed is False
        mock_t.close.assert_called_once()

    @patch("whisper_dic.doctor.create_transcriber")
    def test_close_called_on_success(self, mock_create: MagicMock) -> None:
        mock_t = MagicMock()
        mock_t.health_check.return_value = True
        mock_create.return_value = mock_t

        config = self._make_config("local")
        check_provider(config)

        mock_t.close.assert_called_once()


# ---------------------------------------------------------------------------
# check_groq_api_key
# ---------------------------------------------------------------------------


class TestCheckGroqApiKey:
    def _make_config(
        self, provider: str = "local", api_key: str = "", failover: bool = False
    ) -> AppConfig:
        from whisper_dic.config import (
            AudioFeedbackConfig,
            HotkeyConfig,
            PasteConfig,
            RecordingConfig,
            TextCommandsConfig,
            WhisperConfig,
            WhisperGroqConfig,
            WhisperLocalConfig,
        )

        return AppConfig(
            hotkey=HotkeyConfig(),
            recording=RecordingConfig(),
            paste=PasteConfig(),
            text_commands=TextCommandsConfig(),
            audio_feedback=AudioFeedbackConfig(),
            whisper=WhisperConfig(
                provider=provider,
                failover=failover,
                groq=WhisperGroqConfig(api_key=api_key),
                local=WhisperLocalConfig(),
            ),
        )

    def test_not_applicable_local_no_failover(self) -> None:
        config = self._make_config(provider="local", failover=False)
        assert check_groq_api_key(config) is None

    def test_applicable_groq_provider(self) -> None:
        config = self._make_config(provider="groq", api_key="gsk_abc123xyz789")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is True
        assert "gsk_" in result.message
        assert "789" in result.message

    def test_applicable_failover_enabled(self) -> None:
        config = self._make_config(provider="local", failover=True, api_key="gsk_secretkey99")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is True

    def test_missing_key_groq(self) -> None:
        config = self._make_config(provider="groq", api_key="")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is False
        assert "Not set" in result.message

    def test_whitespace_only_key(self) -> None:
        config = self._make_config(provider="groq", api_key="   ")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is False

    def test_short_key_redacted(self) -> None:
        config = self._make_config(provider="groq", api_key="short")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is True
        assert "***" in result.message

    def test_long_key_partially_shown(self) -> None:
        config = self._make_config(provider="groq", api_key="gsk_abcdefghij1234")
        result = check_groq_api_key(config)
        assert result is not None
        assert result.passed is True
        assert "gsk_" in result.message
        assert "..." in result.message
        assert "1234" in result.message

    def test_fix_message(self) -> None:
        config = self._make_config(provider="groq", api_key="")
        result = check_groq_api_key(config)
        assert result is not None
        assert "whisper-dic set" in result.fix


# ---------------------------------------------------------------------------
# check_microphone
# ---------------------------------------------------------------------------


class TestCheckMicrophone:
    def test_devices_found_with_default(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Mic", "max_input_channels": 2, "index": 0},
            {"name": "Speakers", "max_input_channels": 0, "index": 1},
        ]
        mock_sd.default.device = (0, 1)

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()

        assert result.passed is True
        assert "Built-in Mic" in result.message

    def test_no_input_devices(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "Speakers", "max_input_channels": 0, "index": 0},
        ]

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()

        assert result.passed is False
        assert "No input devices" in result.message

    def test_input_device_not_default(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = [
            {"name": "USB Mic", "max_input_channels": 1, "index": 0},
            {"name": "Other Mic", "max_input_channels": 1, "index": 2},
        ]
        mock_sd.default.device = (5, 1)  # default input index 5 does not match any

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()

        assert result.passed is True
        assert "2 input device(s)" in result.message

    def test_import_error(self) -> None:
        with patch.dict("sys.modules", {"sounddevice": None}):
            result = check_microphone()

        assert result.passed is False
        assert "sounddevice" in result.fix

    def test_query_exception(self) -> None:
        mock_sd = MagicMock()
        mock_sd.query_devices.side_effect = OSError("PortAudio not found")

        with patch.dict("sys.modules", {"sounddevice": mock_sd}):
            result = check_microphone()

        assert result.passed is False
        assert "PortAudio" in result.message


# ---------------------------------------------------------------------------
# check_accessibility
# ---------------------------------------------------------------------------


class TestCheckAccessibility:
    @patch("whisper_dic.doctor.sys")
    def test_non_darwin_returns_none(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "linux"
        assert check_accessibility() is None

    @patch("whisper_dic.compat.check_accessibility", return_value=[])
    @patch("whisper_dic.doctor.sys")
    def test_granted(self, mock_sys: MagicMock, _mock_check: MagicMock) -> None:
        mock_sys.platform = "darwin"
        result = check_accessibility()

        assert result is not None
        assert result.passed is True
        assert "Granted" in result.message

    @patch("whisper_dic.compat.check_accessibility", return_value=["accessibility"])
    @patch("whisper_dic.doctor.sys")
    def test_not_granted(self, mock_sys: MagicMock, _mock_check: MagicMock) -> None:
        mock_sys.platform = "darwin"
        result = check_accessibility()

        assert result is not None
        assert result.passed is False
        assert "Not granted" in result.message
        assert "System Settings" in result.fix

    @patch(
        "whisper_dic.compat.check_accessibility",
        side_effect=RuntimeError("pyobjc missing"),
    )
    @patch("whisper_dic.doctor.sys")
    def test_exception(self, mock_sys: MagicMock, _mock_check: MagicMock) -> None:
        mock_sys.platform = "darwin"
        result = check_accessibility()

        assert result is not None
        assert result.passed is False
        assert "pyobjc missing" in result.message


# ---------------------------------------------------------------------------
# check_local_install
# ---------------------------------------------------------------------------


class TestCheckLocalInstall:
    def test_server_not_found(self, tmp_path: Path) -> None:
        with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
            result = check_local_install()

        assert result.passed is False
        assert "whisper-server not found" in result.message
        assert "setup-local" in result.fix

    def test_server_exists_no_model(self, tmp_path: Path) -> None:
        (tmp_path / "bin").mkdir()
        (tmp_path / "bin" / "whisper-server").touch()
        (tmp_path / "models").mkdir()

        with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
            result = check_local_install()

        assert result.passed is False
        assert "no model" in result.message

    def test_server_and_model_present(self, tmp_path: Path) -> None:
        (tmp_path / "bin").mkdir()
        (tmp_path / "bin" / "whisper-server").touch()
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "ggml-base.bin").touch()

        with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
            result = check_local_install()

        assert result.passed is True
        assert "base" in result.message

    def test_multiple_models(self, tmp_path: Path) -> None:
        (tmp_path / "bin").mkdir()
        (tmp_path / "bin" / "whisper-server").touch()
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "ggml-base.bin").touch()
        (tmp_path / "models" / "ggml-large-v3.bin").touch()

        with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
            result = check_local_install()

        assert result.passed is True
        assert "base" in result.message
        assert "large-v3" in result.message

    def test_models_dir_missing(self, tmp_path: Path) -> None:
        (tmp_path / "bin").mkdir()
        (tmp_path / "bin" / "whisper-server").touch()
        # No models directory at all

        with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
            result = check_local_install()

        assert result.passed is False
        assert "no model" in result.message

    def test_windows_exe_name(self, tmp_path: Path) -> None:
        with patch("whisper_dic.doctor.sys") as mock_sys:
            mock_sys.platform = "win32"
            (tmp_path / "bin").mkdir()
            (tmp_path / "bin" / "whisper-server.exe").touch()
            (tmp_path / "models").mkdir()
            (tmp_path / "models" / "ggml-tiny.bin").touch()

            with patch("whisper_dic.doctor.data_dir", return_value=tmp_path):
                result = check_local_install()

        assert result.passed is True
        assert "tiny" in result.message


# ---------------------------------------------------------------------------
# run_doctor
# ---------------------------------------------------------------------------


class TestRunDoctor:
    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_provider")
    @patch("whisper_dic.doctor.check_groq_api_key")
    @patch("whisper_dic.doctor.check_config")
    def test_all_pass(
        self,
        mock_config: MagicMock,
        mock_groq: MagicMock,
        mock_provider: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_cfg = MagicMock(spec=AppConfig)
        mock_config.return_value = (CheckResult("Config file", True, "ok", ""), fake_cfg)
        mock_provider.return_value = CheckResult("Provider (local)", True, "ok", "")
        mock_groq.return_value = None  # not applicable
        mock_mic.return_value = CheckResult("Microphone", True, "Built-in Mic", "")
        mock_access.return_value = None  # non-darwin
        mock_local.return_value = CheckResult("Local install", True, "ok", "")

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "[ok]" in captured.out
        assert "[FAIL]" not in captured.out

    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_provider")
    @patch("whisper_dic.doctor.check_groq_api_key")
    @patch("whisper_dic.doctor.check_config")
    def test_some_fail(
        self,
        mock_config: MagicMock,
        mock_groq: MagicMock,
        mock_provider: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_cfg = MagicMock(spec=AppConfig)
        mock_config.return_value = (CheckResult("Config file", True, "ok", ""), fake_cfg)
        mock_provider.return_value = CheckResult(
            "Provider (local)", False, "Not reachable", "Start server"
        )
        mock_groq.return_value = None
        mock_mic.return_value = CheckResult("Microphone", True, "Built-in Mic", "")
        mock_access.return_value = None
        mock_local.return_value = CheckResult("Local install", True, "ok", "")

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "Start server" in captured.out

    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_config")
    def test_config_fail_skips_provider(
        self,
        mock_config: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_config.return_value = (
            CheckResult("Config file", False, "Not found", "Run setup"),
            None,
        )
        mock_mic.return_value = CheckResult("Microphone", True, "ok", "")
        mock_access.return_value = None
        mock_local.return_value = CheckResult("Local install", True, "ok", "")

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 1

    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_provider")
    @patch("whisper_dic.doctor.check_groq_api_key")
    @patch("whisper_dic.doctor.check_config")
    def test_groq_key_included_when_applicable(
        self,
        mock_config: MagicMock,
        mock_groq: MagicMock,
        mock_provider: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_cfg = MagicMock(spec=AppConfig)
        mock_config.return_value = (CheckResult("Config file", True, "ok", ""), fake_cfg)
        mock_provider.return_value = CheckResult("Provider (groq)", True, "ok", "")
        mock_groq.return_value = CheckResult("Groq API key", True, "Set (gsk_...)", "")
        mock_mic.return_value = CheckResult("Microphone", True, "ok", "")
        mock_access.return_value = None
        mock_local.return_value = CheckResult("Local install", True, "ok", "")

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Groq API key" in captured.out

    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_provider")
    @patch("whisper_dic.doctor.check_groq_api_key")
    @patch("whisper_dic.doctor.check_config")
    def test_accessibility_included_on_darwin(
        self,
        mock_config: MagicMock,
        mock_groq: MagicMock,
        mock_provider: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_cfg = MagicMock(spec=AppConfig)
        mock_config.return_value = (CheckResult("Config file", True, "ok", ""), fake_cfg)
        mock_provider.return_value = CheckResult("Provider (local)", True, "ok", "")
        mock_groq.return_value = None
        mock_mic.return_value = CheckResult("Microphone", True, "ok", "")
        mock_access.return_value = CheckResult("Accessibility", True, "Granted", "")
        mock_local.return_value = CheckResult("Local install", True, "ok", "")

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Accessibility" in captured.out

    @patch("whisper_dic.doctor.check_local_install")
    @patch("whisper_dic.doctor.check_accessibility")
    @patch("whisper_dic.doctor.check_microphone")
    @patch("whisper_dic.doctor.check_provider")
    @patch("whisper_dic.doctor.check_groq_api_key")
    @patch("whisper_dic.doctor.check_config")
    def test_fix_printed_for_failures(
        self,
        mock_config: MagicMock,
        mock_groq: MagicMock,
        mock_provider: MagicMock,
        mock_mic: MagicMock,
        mock_access: MagicMock,
        mock_local: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        fake_cfg = MagicMock(spec=AppConfig)
        mock_config.return_value = (CheckResult("Config file", True, "ok", ""), fake_cfg)
        mock_provider.return_value = CheckResult("Provider (local)", True, "ok", "")
        mock_groq.return_value = None
        mock_mic.return_value = CheckResult(
            "Microphone", False, "No input devices", "Connect a mic"
        )
        mock_access.return_value = None
        mock_local.return_value = CheckResult(
            "Local install", False, "not found", "Run setup-local"
        )

        exit_code = run_doctor(tmp_path / "config.toml")

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Connect a mic" in captured.out
        assert "Run setup-local" in captured.out


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------


class TestCheckResult:
    def test_fields(self) -> None:
        r = CheckResult(name="Test", passed=True, message="ok", fix="")
        assert r.name == "Test"
        assert r.passed is True
        assert r.message == "ok"
        assert r.fix == ""

    def test_failed_result(self) -> None:
        r = CheckResult(name="Test", passed=False, message="broken", fix="Do this")
        assert r.passed is False
        assert r.fix == "Do this"
