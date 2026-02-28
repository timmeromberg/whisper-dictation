"""Microphone recording utilities for dictation."""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


@dataclass
class RecordingResult:
    """In-memory WAV payload and metadata for a finished recording."""

    wav_bytes: bytes
    duration_seconds: float
    sample_count: int


class Recorder:
    """Capture mono microphone audio and export it as WAV bytes."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        dtype: str = "int16",
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype

        self._lock = threading.Lock()
        self._stream: Optional[sd.InputStream] = None
        self._chunks: list[np.ndarray] = []
        self._recording = False
        self._sample_count = 0
        self._started_at = 0.0

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            print(f"[recorder] stream status: {status}")

        with self._lock:
            if not self._recording:
                return
            self._chunks.append(indata.copy())
            self._sample_count += frames

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
        sf.write(buffer, audio, self.sample_rate, format="WAV", subtype="PCM_16")

        return RecordingResult(
            wav_bytes=buffer.getvalue(),
            duration_seconds=sample_count / float(self.sample_rate),
            sample_count=sample_count,
        )
