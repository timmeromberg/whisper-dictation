"""Tests for Recorder."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from whisper_dic.recorder import Recorder, RecordingResult, reset_audio_backend, strip_long_silence


class TestInitialState:
    def test_not_recording(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert not r.is_recording

    def test_peak_is_zero(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert r.read_peak() == 0.0

    def test_stop_returns_none(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert r.stop() is None


class TestCallback:
    def test_accumulates_chunks(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder(sample_rate=16000)
            r._recording = True
            data = np.array([[100], [200], [-300]], dtype=np.int16)
            r._callback(data, 3, None, None)
            assert len(r._chunks) == 1
            assert r._sample_count == 3

    def test_tracks_peak(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            r._recording = True
            data = np.array([[500], [-1000], [200]], dtype=np.int16)
            r._callback(data, 3, None, None)
            assert r._peak == 1000.0

    def test_ignored_when_not_recording(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            r._recording = False
            data = np.array([[100]], dtype=np.int16)
            r._callback(data, 1, None, None)
            assert len(r._chunks) == 0

    def test_read_peak_resets(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            r._recording = True
            data = np.array([[500]], dtype=np.int16)
            r._callback(data, 1, None, None)
            peak = r.read_peak()
            assert peak == 500.0
            assert r.read_peak() == 0.0  # reset after read


class TestStartStop:
    def test_start_creates_stream(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder(sample_rate=16000)
            assert r.start() is True
            assert r.is_recording
            mock_sd.InputStream.assert_called_once()
            mock_stream.start.assert_called_once()
            r.stop()

    def test_start_when_already_recording(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            assert r.start() is True
            assert r.start() is False
            r.stop()

    def test_start_failure_resets(self) -> None:
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.side_effect = RuntimeError("No device")
            r = Recorder()
            with pytest.raises(RuntimeError):
                r.start()
            assert not r.is_recording

    def test_stop_returns_result(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd, patch("whisper_dic.recorder.sf") as mock_sf:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder(sample_rate=16000)
            r.start()
            # Simulate callback
            data = np.zeros((1600, 1), dtype=np.int16)
            r._callback(data, 1600, None, None)
            # Mock sf.write
            def fake_write(buf, audio, sr, format):
                buf.write(b"FLAC-fake-data")
            mock_sf.write.side_effect = fake_write
            result = r.stop()
            assert result is not None
            assert isinstance(result, RecordingResult)
            assert result.sample_count == 1600
            assert result.duration_seconds == pytest.approx(0.1, abs=0.01)
            assert len(result.audio_bytes) > 0

    def test_stop_no_chunks_returns_none(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            r.start()
            result = r.stop()
            assert result is None


class TestResetAudioBackend:
    def test_calls_terminate_and_initialize(self) -> None:
        with patch("whisper_dic.recorder.sd") as mock_sd:
            reset_audio_backend()
            mock_sd._terminate.assert_called_once()
            mock_sd._initialize.assert_called_once()

    def test_terminate_called_before_initialize(self) -> None:
        with patch("whisper_dic.recorder.sd") as mock_sd:
            call_order: list[str] = []
            mock_sd._terminate.side_effect = lambda: call_order.append("terminate")
            mock_sd._initialize.side_effect = lambda: call_order.append("initialize")
            reset_audio_backend()
            assert call_order == ["terminate", "initialize"]

    def test_handles_terminate_exception(self) -> None:
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd._terminate.side_effect = RuntimeError("PortAudio error")
            # Should not raise — logs and swallows the error
            reset_audio_backend()

    def test_handles_initialize_exception(self) -> None:
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd._initialize.side_effect = RuntimeError("PortAudio error")
            reset_audio_backend()


class TestStreamWatchdog:
    """Tests for stream liveness detection and restart."""

    def test_seconds_since_last_callback_zero_when_not_recording(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert r.seconds_since_last_callback == 0.0

    def test_seconds_since_last_callback_tracks_time(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            r.start()
            # Simulate callback
            data = np.zeros((160, 1), dtype=np.int16)
            r._callback(data, 160, None, None)
            # Should be very small (just happened)
            assert r.seconds_since_last_callback < 0.5

    def test_seconds_since_last_callback_grows_without_callbacks(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            r.start()
            # Fake last callback time to 3 seconds ago
            with r._lock:
                r._last_callback_time = time.monotonic() - 3.0
            assert r.seconds_since_last_callback >= 2.5

    def test_restart_stream_reopens_stream(self) -> None:
        mock_stream1 = MagicMock()
        mock_stream2 = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.side_effect = [mock_stream1, mock_stream2]
            r = Recorder()
            r.start()
            # Simulate some recorded audio
            data = np.zeros((160, 1), dtype=np.int16)
            r._callback(data, 160, None, None)

            with patch("whisper_dic.recorder.reset_audio_backend"):
                result = r.restart_stream()

            assert result is True
            mock_stream1.stop.assert_called_once()
            mock_stream1.close.assert_called_once()
            mock_stream2.start.assert_called_once()

    def test_restart_stream_preserves_chunks(self) -> None:
        mock_stream1 = MagicMock()
        mock_stream2 = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.side_effect = [mock_stream1, mock_stream2]
            r = Recorder()
            r.start()
            data = np.ones((160, 1), dtype=np.int16) * 1000
            r._callback(data, 160, None, None)
            chunks_before = len(r._chunks)

            with patch("whisper_dic.recorder.reset_audio_backend"):
                r.restart_stream()

            # Chunks from before restart should still be there
            assert len(r._chunks) >= chunks_before

    def test_restart_stream_returns_false_when_not_recording(self) -> None:
        with patch("whisper_dic.recorder.sd"):
            r = Recorder()
            assert r.restart_stream() is False

    def test_stream_errors_tracked(self) -> None:
        mock_stream = MagicMock()
        with patch("whisper_dic.recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            r.start()
            # Callback with status error
            r._callback(np.zeros((160, 1), dtype=np.int16), 160, None, "input overflow")
            assert r._stream_errors == 1


class TestStripLongSilence:
    """Tests for silence compression before Whisper transcription."""

    RATE = 16000

    def _tone(self, seconds: float, freq: float = 440.0) -> np.ndarray:
        """Generate a short tone as int16."""
        t = np.linspace(0, seconds, int(self.RATE * seconds), endpoint=False)
        return (np.sin(2.0 * np.pi * freq * t) * 16000).astype(np.int16)

    def _silence(self, seconds: float) -> np.ndarray:
        """Generate silence as int16."""
        return np.zeros(int(self.RATE * seconds), dtype=np.int16)

    def test_short_silence_preserved(self) -> None:
        """Silence shorter than threshold is kept intact."""
        audio = np.concatenate([self._tone(0.5), self._silence(0.5), self._tone(0.5)])
        result = strip_long_silence(audio, self.RATE, max_silence_seconds=1.0)
        # Short silence is preserved — output should be roughly the same length
        assert len(result) >= len(audio) * 0.9

    def test_long_silence_compressed(self) -> None:
        """Silence longer than threshold is compressed to keep_seconds."""
        tone = self._tone(0.5)
        silence = self._silence(3.0)  # 3s gap
        audio = np.concatenate([tone, silence, tone])
        result = strip_long_silence(audio, self.RATE, max_silence_seconds=1.0, keep_seconds=0.3)
        # 3s silence → 0.3s — output should be much shorter
        expected_max = len(tone) * 2 + int(self.RATE * 0.5)
        assert len(result) < expected_max

    def test_voiced_content_preserved(self) -> None:
        """All voiced segments survive silence stripping."""
        tone1 = self._tone(0.5, freq=440.0)
        tone2 = self._tone(0.5, freq=880.0)
        silence = self._silence(3.0)
        audio = np.concatenate([tone1, silence, tone2])
        result = strip_long_silence(audio, self.RATE, max_silence_seconds=1.0)
        # Both tones should be present — total voiced samples preserved
        voiced_original = len(tone1) + len(tone2)
        assert len(result) >= voiced_original

    def test_no_silence_passthrough(self) -> None:
        """Audio with no silence passes through unchanged."""
        audio = self._tone(2.0)
        result = strip_long_silence(audio, self.RATE)
        assert len(result) == len(audio)

    def test_all_silence_compressed(self) -> None:
        """Pure silence is compressed to keep_seconds."""
        audio = self._silence(5.0)
        result = strip_long_silence(audio, self.RATE, max_silence_seconds=1.0, keep_seconds=0.3)
        assert len(result) < len(audio)

    def test_multiple_gaps_each_compressed(self) -> None:
        """Multiple long gaps are each independently compressed."""
        tone = self._tone(0.3)
        silence = self._silence(2.0)
        audio = np.concatenate([tone, silence, tone, silence, tone])
        original_len = len(audio)
        result = strip_long_silence(audio, self.RATE, max_silence_seconds=1.0, keep_seconds=0.3)
        # Two 2s gaps → two 0.3s gaps — should save ~3.4s of samples
        assert len(result) < original_len * 0.7

    def test_2d_audio_array(self) -> None:
        """Works with 2D mono arrays (N, 1) from sounddevice."""
        audio_1d = np.concatenate([self._tone(0.5), self._silence(3.0), self._tone(0.5)])
        audio_2d = audio_1d.reshape(-1, 1)
        result = strip_long_silence(audio_2d, self.RATE, max_silence_seconds=1.0)
        assert len(result) < len(audio_2d)
