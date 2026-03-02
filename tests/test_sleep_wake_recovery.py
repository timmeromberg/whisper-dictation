"""Tests for sleep/wake microphone recovery behavior."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from whisper_dic.config import (
    AppConfig,
    AudioFeedbackConfig,
    HotkeyConfig,
    PasteConfig,
    RecordingConfig,
    RewriteConfig,
    TextCommandsConfig,
    WhisperConfig,
)


def _make_config() -> AppConfig:
    return AppConfig(
        hotkey=HotkeyConfig(),
        recording=RecordingConfig(),
        paste=PasteConfig(),
        text_commands=TextCommandsConfig(),
        whisper=WhisperConfig(),
        audio_feedback=AudioFeedbackConfig(enabled=False),
        rewrite=RewriteConfig(enabled=False, mode="light"),
    )


class TestHoldStartRetryOnStreamFailure:
    """Test that _on_hold_start retries after resetting audio backend."""

    def _make_app(self):
        config = _make_config()
        listener = SimpleNamespace(start=MagicMock(), stop=MagicMock(), set_key=MagicMock())
        transcriber = MagicMock()
        transcriber.language = "en"
        transcriber.health_check.return_value = True

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener", return_value=listener),
            patch("whisper_dic.dictation.create_transcriber", return_value=transcriber),
        ):
            from whisper_dic.dictation import DictationApp

            app = DictationApp(config)
        app.on_state_change = MagicMock()
        app.audio_controller = MagicMock()
        return app

    def test_retry_succeeds_after_reset(self) -> None:
        app = self._make_app()
        # First call fails, second succeeds
        app.recorder.start = MagicMock(side_effect=[RuntimeError("Device not found"), True])

        with patch("whisper_dic.dictation.reset_audio_backend") as mock_reset:
            app._on_hold_start()

        mock_reset.assert_called_once()
        assert app.recorder.start.call_count == 2
        # Recording should have started successfully
        app.on_state_change.assert_any_call("recording", "")

    def test_retry_also_fails_shows_notification(self) -> None:
        app = self._make_app()
        # Both calls fail
        app.recorder.start = MagicMock(side_effect=RuntimeError("Device not found"))

        with patch("whisper_dic.dictation.reset_audio_backend") as mock_reset:
            app._on_hold_start()

        mock_reset.assert_called_once()
        assert app.recorder.start.call_count == 2
        # Should emit idle state on failure
        app.on_state_change.assert_any_call("idle", "")

    def test_retry_also_fails_sends_notification(self) -> None:
        app = self._make_app()
        app.recorder.start = MagicMock(side_effect=RuntimeError("Device not found"))
        app._notify = MagicMock()

        with patch("whisper_dic.dictation.reset_audio_backend"):
            app._on_hold_start()

        app._notify.assert_called_once()
        assert "Microphone unavailable" in app._notify.call_args[0][0]

    def test_no_retry_when_start_succeeds_first_time(self) -> None:
        app = self._make_app()
        app.recorder.start = MagicMock(return_value=True)

        with patch("whisper_dic.dictation.reset_audio_backend") as mock_reset:
            app._on_hold_start()

        mock_reset.assert_not_called()
        app.recorder.start.assert_called_once()
        app.on_state_change.assert_any_call("recording", "")

    def test_no_retry_when_stopped(self) -> None:
        app = self._make_app()
        app._stop_event.set()
        app.recorder.start = MagicMock()

        with patch("whisper_dic.dictation.reset_audio_backend") as mock_reset:
            app._on_hold_start()

        mock_reset.assert_not_called()
        app.recorder.start.assert_not_called()

    def test_start_done_event_set_after_failure(self) -> None:
        app = self._make_app()
        app.recorder.start = MagicMock(side_effect=RuntimeError("Device not found"))

        with patch("whisper_dic.dictation.reset_audio_backend"):
            app._on_hold_start()

        # _start_done must be set even on failure (prevents hold_end deadlock)
        assert app._start_done.is_set()


@pytest.mark.skipif(sys.platform != "darwin", reason="wake observer is macOS-only")
class TestWakeObserver:
    """Test menubar wake-from-sleep observer."""

    def test_on_wake_resets_audio_and_rebuilds_mic_menu(self) -> None:
        from whisper_dic.menubar import DictationMenuBar

        app = DictationMenuBar.__new__(DictationMenuBar)
        app._known_input_devices = {"Built-in Microphone"}
        app._get_input_device_names = MagicMock(return_value={"USB Microphone"})
        app._rebuild_mic_menu = MagicMock()

        with (
            patch("whisper_dic.menubar.callAfter") as mock_call_after,
            patch("whisper_dic.recorder.reset_audio_backend") as mock_reset,
        ):
            app._on_wake()

        mock_reset.assert_called_once()
        assert app._known_input_devices == {"USB Microphone"}
        mock_call_after.assert_called_once_with(app._rebuild_mic_menu)

    def test_register_wake_observer_handles_import_error(self) -> None:
        from whisper_dic.menubar import DictationMenuBar

        app = DictationMenuBar.__new__(DictationMenuBar)

        with patch.dict("sys.modules", {"AppKit": None}):
            # Should not raise — logs and swallows the error
            app._register_wake_observer()

    def test_register_wake_observer_handles_runtime_error(self) -> None:
        from whisper_dic.menubar import DictationMenuBar

        app = DictationMenuBar.__new__(DictationMenuBar)
        mock_appkit = MagicMock()
        mock_appkit.NSWorkspace.sharedWorkspace.side_effect = RuntimeError("no workspace")

        with patch.dict("sys.modules", {"AppKit": mock_appkit}):
            # Should not raise
            app._register_wake_observer()
