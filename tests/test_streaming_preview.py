"""Tests for streaming transcription preview."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import numpy as np

from whisper_dic.recorder import Recorder


class TestGetAccumulatedAudio:
    def test_returns_none_when_not_recording(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert r.get_accumulated_audio() is None

    def test_returns_none_when_no_chunks(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            r._recording = True
            assert r.get_accumulated_audio() is None

    def test_returns_flac_bytes_with_chunks(self) -> None:
        with patch("whisper_dic.recorder.sd"), patch("whisper_dic.recorder.sf") as mock_sf:
            r = Recorder(sample_rate=16000)
            r._recording = True
            data = np.zeros((1600, 1), dtype=np.int16)
            r._chunks = [data]
            r._sample_count = 1600

            def fake_write(buf, audio, sr, format):
                buf.write(b"FLAC-preview-data")

            mock_sf.write.side_effect = fake_write
            result = r.get_accumulated_audio()
            assert result is not None
            assert result == b"FLAC-preview-data"

    def test_does_not_clear_chunks(self) -> None:
        """get_accumulated_audio should snapshot, not consume chunks."""
        with patch("whisper_dic.recorder.sd"), patch("whisper_dic.recorder.sf") as mock_sf:
            r = Recorder(sample_rate=16000)
            r._recording = True
            data = np.zeros((1600, 1), dtype=np.int16)
            r._chunks = [data]
            r._sample_count = 1600

            def fake_write(buf, audio, sr, format):
                buf.write(b"data")

            mock_sf.write.side_effect = fake_write
            r.get_accumulated_audio()
            assert len(r._chunks) == 1  # chunks still there


class TestPreviewLoop:
    def test_preview_loop_stops_on_event(self) -> None:
        """Preview loop should exit when stop event is set."""
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            config = MagicMock()
            config.recording.sample_rate = 16000
            config.recording.device = None
            config.recording.min_duration = 0.3
            config.recording.max_duration = 300.0
            config.recording.streaming_preview = True
            config.recording.preview_interval = 0.1
            config.text_commands.enabled = True
            config.paste.auto_send = False
            config.whisper.provider = "local"
            config.whisper.language = "en"
            config.whisper.languages = ["en"]
            config.whisper.timeout_seconds = 120.0
            config.whisper.prompt = ""
            config.whisper.failover = False
            config.whisper.local.url = "http://localhost:2022/v1/audio/transcriptions"
            config.whisper.local.model = "large-v3"
            config.whisper.groq.api_key = ""
            config.hotkey.key = "left_option"
            config.audio_feedback.enabled = False
            config.audio_feedback.start_frequency = 880.0
            config.audio_feedback.stop_frequency = 660.0
            config.audio_feedback.volume = 0.0
            config.audio_feedback.duration_seconds = 0.08
            config.audio_control.enabled = False
            config.audio_control.mute_local = False
            config.audio_control.devices = []
            config.rewrite.enabled = False
            config.rewrite.mode = "light"
            config.rewrite.model = "llama-3.3-70b-versatile"
            config.rewrite.prompt = ""
            config.custom_commands = {}

            app = DictationApp(config)

            mock_transcriber = MagicMock()
            mock_transcriber.transcribe.return_value = "hello world"
            app._preview_transcriber = mock_transcriber

            # Start preview loop
            app._preview_stop.clear()
            thread = threading.Thread(target=app._run_preview_loop, daemon=True)
            thread.start()

            # Let it run briefly then stop
            threading.Event().wait(0.3)
            app._preview_stop.set()
            thread.join(timeout=2.0)
            assert not thread.is_alive()

    def test_preview_failure_does_not_crash(self) -> None:
        """Preview transcription errors should be caught, not propagated."""
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            config = MagicMock()
            config.recording.sample_rate = 16000
            config.recording.device = None
            config.recording.min_duration = 0.3
            config.recording.max_duration = 300.0
            config.recording.streaming_preview = True
            config.recording.preview_interval = 0.1
            config.text_commands.enabled = True
            config.paste.auto_send = False
            config.whisper.provider = "local"
            config.whisper.language = "en"
            config.whisper.languages = ["en"]
            config.whisper.timeout_seconds = 120.0
            config.whisper.prompt = ""
            config.whisper.failover = False
            config.whisper.local.url = "http://localhost:2022/v1/audio/transcriptions"
            config.whisper.local.model = "large-v3"
            config.whisper.groq.api_key = ""
            config.hotkey.key = "left_option"
            config.audio_feedback.enabled = False
            config.audio_feedback.start_frequency = 880.0
            config.audio_feedback.stop_frequency = 660.0
            config.audio_feedback.volume = 0.0
            config.audio_feedback.duration_seconds = 0.08
            config.audio_control.enabled = False
            config.audio_control.mute_local = False
            config.audio_control.devices = []
            config.rewrite.enabled = False
            config.rewrite.mode = "light"
            config.rewrite.model = "llama-3.3-70b-versatile"
            config.rewrite.prompt = ""
            config.custom_commands = {}

            app = DictationApp(config)

            # Simulate accumulated audio available
            app.recorder.get_accumulated_audio = MagicMock(return_value=b"audio")

            mock_transcriber = MagicMock()
            mock_transcriber.transcribe.side_effect = RuntimeError("API error")
            app._preview_transcriber = mock_transcriber

            app._preview_stop.clear()
            thread = threading.Thread(target=app._run_preview_loop, daemon=True)
            thread.start()

            # Let it run and fail, then stop
            threading.Event().wait(0.3)
            app._preview_stop.set()
            thread.join(timeout=2.0)
            assert not thread.is_alive()  # Should not crash
