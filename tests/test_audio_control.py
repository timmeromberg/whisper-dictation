"""Tests for AudioController and device types."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from audio_control import (
    AdbDevice,
    AudioControlConfig,
    AudioController,
    CustomDevice,
    LocalMacDevice,
    _adb_devices,
)


class TestAudioControlConfig:
    def test_defaults(self) -> None:
        config = AudioControlConfig()
        assert config.enabled is False
        assert config.mute_local is True
        assert config.devices == []


class TestControllerDisabled:
    def test_mute_noop(self) -> None:
        config = AudioControlConfig(enabled=False)
        ctrl = AudioController(config)
        ctrl.mute()  # should not raise
        ctrl.unmute()


class TestControllerEnabled:
    @pytest.mark.skipif(sys.platform != "darwin", reason="LocalMacDevice only on macOS")
    def test_creates_local_device(self) -> None:
        config = AudioControlConfig(enabled=True, mute_local=True)
        ctrl = AudioController(config)
        assert len(ctrl._devices) == 1
        assert isinstance(ctrl._devices[0], LocalMacDevice)

    def test_no_local_if_disabled(self) -> None:
        config = AudioControlConfig(enabled=True, mute_local=False)
        ctrl = AudioController(config)
        assert len(ctrl._devices) == 0

    def test_custom_device(self) -> None:
        config = AudioControlConfig(
            enabled=True, mute_local=False,
            devices=[{"type": "custom", "name": "Test", "mute_command": "echo mute", "unmute_command": "echo unmute"}],
        )
        ctrl = AudioController(config)
        assert len(ctrl._devices) == 1
        assert isinstance(ctrl._devices[0], CustomDevice)

    def test_adb_device(self) -> None:
        config = AudioControlConfig(
            enabled=True, mute_local=False,
            devices=[{"type": "adb", "name": "Phone", "serial": "abc123"}],
        )
        ctrl = AudioController(config)
        assert len(ctrl._devices) == 1
        assert isinstance(ctrl._devices[0], AdbDevice)

    def test_unknown_type_skipped(self) -> None:
        config = AudioControlConfig(
            enabled=True, mute_local=False,
            devices=[{"type": "bluetooth", "name": "Speaker"}],
        )
        ctrl = AudioController(config)
        assert len(ctrl._devices) == 0


@pytest.mark.skipif(sys.platform != "darwin", reason="LocalMacDevice uses osascript")
class TestLocalMacDevice:
    def test_mute_calls_osascript(self) -> None:
        dev = LocalMacDevice()
        with patch("audio_control.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="output volume:50, input volume:50, alert volume:100, output muted:false\n"
            )
            dev.mute()
            assert mock_run.call_count == 2  # get settings + set muted

    def test_unmute_skips_when_was_muted(self) -> None:
        dev = LocalMacDevice()
        dev._was_muted = True
        with patch("audio_control.subprocess.run") as mock_run:
            dev.unmute()
            mock_run.assert_not_called()

    def test_unmute_restores_volume(self) -> None:
        dev = LocalMacDevice()
        dev._was_muted = False
        dev._saved_volume = 42
        with patch("audio_control.subprocess.run") as mock_run:
            dev.unmute()
            assert mock_run.call_count == 2  # unmute + restore volume


class TestCustomDevice:
    def test_mute_runs_command(self) -> None:
        dev = CustomDevice(name="Test", mute_command="echo mute", unmute_command="echo unmute")
        with patch("audio_control.subprocess.run") as mock_run:
            dev.mute()
            mock_run.assert_called_once()

    def test_unmute_runs_command(self) -> None:
        dev = CustomDevice(name="Test", mute_command="echo mute", unmute_command="echo unmute")
        with patch("audio_control.subprocess.run") as mock_run:
            dev.unmute()
            mock_run.assert_called_once()

    def test_mute_failure_does_not_raise(self) -> None:
        dev = CustomDevice(name="Test", mute_command="nonexistent", unmute_command="echo ok")
        with patch("audio_control.subprocess.run", side_effect=Exception("fail")):
            dev.mute()  # should not raise


class TestAdbDevices:
    def test_parses_device_list(self) -> None:
        fake_output = "List of devices attached\nabc123  device model:Pixel_7\n"
        with patch("audio_control.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output)
            devices = _adb_devices()
            assert len(devices) == 1
            assert devices[0] == ("abc123", "Pixel_7")

    def test_no_adb_returns_empty(self) -> None:
        with patch("audio_control.subprocess.run", side_effect=Exception("no adb")):
            assert _adb_devices() == []

    def test_no_devices_returns_empty(self) -> None:
        with patch("audio_control.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="List of devices attached\n\n")
            assert _adb_devices() == []

    def test_multiple_devices(self) -> None:
        fake_output = (
            "List of devices attached\n"
            "abc123  device model:Pixel_7\n"
            "def456  device model:Galaxy_S23\n"
        )
        with patch("audio_control.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output)
            devices = _adb_devices()
            assert len(devices) == 2
