"""Tests for Recorder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from whisper_dic.recorder import Recorder, RecordingResult


class TestInitialState:
    def test_not_recording(self) -> None:
        with patch("recorder.sd"):
            r = Recorder()
            assert not r.is_recording

    def test_peak_is_zero(self) -> None:
        with patch("recorder.sd"):
            r = Recorder()
            assert r.read_peak() == 0.0

    def test_stop_returns_none(self) -> None:
        with patch("recorder.sd"):
            r = Recorder()
            assert r.stop() is None


class TestCallback:
    def test_accumulates_chunks(self) -> None:
        with patch("recorder.sd"):
            r = Recorder(sample_rate=16000)
            r._recording = True
            data = np.array([[100], [200], [-300]], dtype=np.int16)
            r._callback(data, 3, None, None)
            assert len(r._chunks) == 1
            assert r._sample_count == 3

    def test_tracks_peak(self) -> None:
        with patch("recorder.sd"):
            r = Recorder()
            r._recording = True
            data = np.array([[500], [-1000], [200]], dtype=np.int16)
            r._callback(data, 3, None, None)
            assert r._peak == 1000.0

    def test_ignored_when_not_recording(self) -> None:
        with patch("recorder.sd"):
            r = Recorder()
            r._recording = False
            data = np.array([[100]], dtype=np.int16)
            r._callback(data, 1, None, None)
            assert len(r._chunks) == 0

    def test_read_peak_resets(self) -> None:
        with patch("recorder.sd"):
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
        with patch("recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder(sample_rate=16000)
            assert r.start() is True
            assert r.is_recording
            mock_sd.InputStream.assert_called_once()
            mock_stream.start.assert_called_once()
            r.stop()

    def test_start_when_already_recording(self) -> None:
        mock_stream = MagicMock()
        with patch("recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            assert r.start() is True
            assert r.start() is False
            r.stop()

    def test_start_failure_resets(self) -> None:
        with patch("recorder.sd") as mock_sd:
            mock_sd.InputStream.side_effect = RuntimeError("No device")
            r = Recorder()
            with pytest.raises(RuntimeError):
                r.start()
            assert not r.is_recording

    def test_stop_returns_result(self) -> None:
        mock_stream = MagicMock()
        with patch("recorder.sd") as mock_sd, patch("recorder.sf") as mock_sf:
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
        with patch("recorder.sd") as mock_sd:
            mock_sd.InputStream.return_value = mock_stream
            r = Recorder()
            r.start()
            result = r.stop()
            assert result is None
