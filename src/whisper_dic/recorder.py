"""Microphone recording utilities for dictation."""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


@dataclass
class RecordingResult:
    """In-memory WAV payload and metadata for a finished recording."""

    audio_bytes: bytes
    duration_seconds: float
    sample_count: int


class Recorder:
    """Capture mono microphone audio and export it as WAV bytes."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
        device: str | int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.device = device

        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._sample_count = 0
        self._started_at = 0.0
        self._peak: float = 0.0

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def read_peak(self) -> float:
        """Read and reset peak amplitude (0.0-1.0 for float, 0-32768 for int16)."""
        with self._lock:
            peak = self._peak
            self._peak = 0.0
            return peak

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        if status:
            print(f"[recorder] stream status: {status}")

        with self._lock:
            if not self._recording:
                return
            self._chunks.append(indata.copy())
            self._sample_count += frames
            # Track peak amplitude for level metering
            self._peak = max(self._peak, float(np.abs(indata).max()))

    def start(self) -> bool:
        with self._lock:
            if self._recording:
                return False

            self._chunks = []
            self._sample_count = 0
            self._started_at = time.monotonic()
            self._recording = True

            try:
                self._stream = sd.InputStream(
                    device=self.device,
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=self.dtype,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception:
                self._recording = False
                self._stream = None
                raise

        return True

    def stop(self) -> Optional[RecordingResult]:
        with self._lock:
            if not self._recording:
                return None

            stream = self._stream
            self._stream = None
            self._recording = False

        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            chunks = self._chunks
            self._chunks = []
            sample_count = self._sample_count

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0)
        buffer = io.BytesIO()
        sf.write(buffer, audio, self.sample_rate, format="FLAC")

        return RecordingResult(
            audio_bytes=buffer.getvalue(),
            duration_seconds=sample_count / float(self.sample_rate),
            sample_count=sample_count,
        )

    def __del__(self) -> None:
        """Safety net: close stream if not already closed."""
        stream = self._stream
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
