"""Tests for streaming transcription preview."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np

from whisper_dic.recorder import Recorder, RecordingResult


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

    def test_uses_incremental_cache(self) -> None:
        with patch("whisper_dic.recorder.sd"), patch("whisper_dic.recorder.sf") as mock_sf:
            r = Recorder(sample_rate=16000)
            r._recording = True
            first = np.zeros((800, 1), dtype=np.int16)
            second = np.ones((800, 1), dtype=np.int16)
            r._chunks = [first]

            def fake_write(buf, audio, sr, format):
                buf.write(b"x")

            mock_sf.write.side_effect = fake_write
            r.get_accumulated_audio()
            cache_after_first = r._combined_cache.copy()
            assert r._combined_chunk_count == 1

            r._chunks.append(second)
            r.get_accumulated_audio()
            assert r._combined_chunk_count == 2
            assert r._combined_cache is not None
            assert len(r._combined_cache) == 1600
            assert len(cache_after_first) == 800


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
            config.hotkey.double_tap_window = 0.5
            config.paste.pre_paste_delay = 0.05
            config.paste.clipboard_restore_delay = 0.3
            config.audio_feedback.enabled = False
            config.audio_feedback.start_frequency = 880.0
            config.audio_feedback.stop_frequency = 660.0
            config.audio_feedback.cancel_frequency = 440.0
            config.audio_feedback.language_frequency = 1200.0
            config.audio_feedback.command_frequency = 1320.0
            config.audio_feedback.auto_send_frequency = 1100.0
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
            config.snippets = {}

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
            config.hotkey.double_tap_window = 0.5
            config.paste.pre_paste_delay = 0.05
            config.paste.clipboard_restore_delay = 0.3
            config.audio_feedback.enabled = False
            config.audio_feedback.start_frequency = 880.0
            config.audio_feedback.stop_frequency = 660.0
            config.audio_feedback.cancel_frequency = 440.0
            config.audio_feedback.language_frequency = 1200.0
            config.audio_feedback.command_frequency = 1320.0
            config.audio_feedback.auto_send_frequency = 1100.0
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
            config.snippets = {}

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


def _base_config() -> MagicMock:
    config = MagicMock()
    config.recording.sample_rate = 16000
    config.recording.device = None
    config.recording.min_duration = 0.3
    config.recording.max_duration = 300.0
    config.recording.streaming_preview = True
    config.recording.preview_interval = 0.1
    config.recording.preview_provider = ""
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
    config.hotkey.double_tap_window = 0.5
    config.paste.pre_paste_delay = 0.05
    config.paste.clipboard_restore_delay = 0.3
    config.audio_feedback.enabled = False
    config.audio_feedback.start_frequency = 880.0
    config.audio_feedback.stop_frequency = 660.0
    config.audio_feedback.cancel_frequency = 440.0
    config.audio_feedback.language_frequency = 1200.0
    config.audio_feedback.command_frequency = 1320.0
    config.audio_feedback.auto_send_frequency = 1100.0
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
    config.snippets = {}
    return config


class TestPreviewShutdown:
    def test_stop_joins_preview_thread_before_close(self) -> None:
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            app = DictationApp(_base_config())
            app._preview_stop.clear()
            t = threading.Thread(target=lambda: app._preview_stop.wait(5.0), daemon=True)
            app._preview_thread = t
            t.start()

            preview = MagicMock()
            app._preview_transcriber = preview

            app.stop()

            assert not t.is_alive()
            preview.close.assert_called_once()


class _BlockingTranscriber:
    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self.language = "en"
        self._started = started
        self._release = release
        self.closed = False

    def health_check(self) -> bool:
        return True

    def transcribe(self, _audio_bytes: bytes) -> str:
        self._started.set()
        self._release.wait(timeout=2.0)
        return "ok"

    def close(self) -> None:
        self.closed = True


class TestTranscriberSwapLock:
    def test_replace_transcriber_waits_for_in_flight_transcription(self) -> None:
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            app = DictationApp(_base_config())

            started = threading.Event()
            release = threading.Event()
            blocking = _BlockingTranscriber(started, release)
            app.replace_transcriber(blocking)

            result_holder: dict[str, str] = {}

            def _transcribe() -> None:
                result_holder["text"] = app._transcribe_with_retry(b"audio", max_attempts=1)

            tx_thread = threading.Thread(target=_transcribe, daemon=True)
            tx_thread.start()
            assert started.wait(timeout=1.0)

            next_transcriber = MagicMock()
            next_transcriber.language = "en"
            next_transcriber.health_check.return_value = True
            next_transcriber.transcribe.return_value = "new"

            swap_done = threading.Event()

            def _swap() -> None:
                app.replace_transcriber(next_transcriber)
                swap_done.set()

            swap_thread = threading.Thread(target=_swap, daemon=True)
            swap_thread.start()

            # Swap must wait while transcribe() is still running.
            assert not swap_done.wait(timeout=0.2)

            release.set()
            tx_thread.join(timeout=1.0)
            swap_thread.join(timeout=1.0)

            assert result_holder["text"] == "ok"
            assert swap_done.is_set()
            assert blocking.closed is True

    def test_reset_preview_transcriber_waits_for_in_flight_preview_transcription(self) -> None:
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            app = DictationApp(_base_config())
            app.recorder.get_accumulated_audio = MagicMock(return_value=b"audio")

            started = threading.Event()
            release = threading.Event()
            blocking = _BlockingTranscriber(started, release)
            app._preview_transcriber = blocking

            preview_done = threading.Event()

            def _preview() -> None:
                app._do_preview()
                preview_done.set()

            preview_thread = threading.Thread(target=_preview, daemon=True)
            preview_thread.start()
            assert started.wait(timeout=1.0)

            reset_done = threading.Event()

            def _reset() -> None:
                app.reset_preview_transcriber()
                reset_done.set()

            reset_thread = threading.Thread(target=_reset, daemon=True)
            reset_thread.start()

            # Reset must wait while preview transcribe() is still running.
            assert not reset_done.wait(timeout=0.2)

            release.set()
            preview_thread.join(timeout=1.0)
            reset_thread.join(timeout=1.0)

            assert preview_done.is_set()
            assert reset_done.is_set()
            assert app._preview_transcriber is None
            assert blocking.closed is True


class TestTapDetection:
    def test_short_tap_uses_physical_hold_duration(self) -> None:
        """Short tap detection should use key hold time, not debounce-extended audio duration."""
        from whisper_dic.dictation import DictationApp

        with (
            patch("whisper_dic.recorder.sd"),
            patch("whisper_dic.dictation.HotkeyListener"),
            patch("whisper_dic.dictation.check_accessibility", return_value=[]),
        ):
            app = DictationApp(_base_config())
            app._stop_preview = MagicMock()
            app.audio_controller.unmute = MagicMock()
            app.play_beep = MagicMock()
            app._emit_state = MagicMock()
            app._cycle_language = MagicMock()
            app._last_tap_time = time.monotonic()
            app._languages = ["en", "de"]
            app.recorder.stop = MagicMock(
                return_value=RecordingResult(
                    audio_bytes=b"audio",
                    duration_seconds=1.2,  # Includes debounce tail.
                    sample_count=19200,
                ),
            )

            app._on_hold_end(auto_send=False, command_mode=False, hold_duration_seconds=0.05)

            app._cycle_language.assert_called_once_with()
            app._emit_state.assert_called_with("idle")
