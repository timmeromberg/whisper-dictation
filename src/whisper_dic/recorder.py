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


def strip_long_silence(
    audio: np.ndarray,
    sample_rate: int,
    silence_threshold: float = 0.02,
    max_silence_seconds: float = 1.0,
    keep_seconds: float = 0.3,
) -> np.ndarray:
    """Replace silence gaps longer than *max_silence_seconds* with *keep_seconds* of silence.

    Whisper models lose context when there are long silent stretches in the
    middle of a recording — the attention mechanism drifts and the model
    either hallucinates or skips the remainder.  By collapsing long gaps we
    keep all voiced content intact while removing the problematic dead air.

    *silence_threshold* is relative to the int16 range (0–32768).
    """
    if audio.ndim == 2:
        mono = audio[:, 0]
    else:
        mono = audio

    # Energy per frame — for int16 data the values are in [−32768, 32767].
    # Normalize so 1.0 = full scale.
    if np.issubdtype(audio.dtype, np.integer):
        energy = np.abs(mono.astype(np.float32)) / 32768.0
    else:
        energy = np.abs(mono)

    frame_size = int(sample_rate * 0.02)  # 20 ms frames
    keep_frames = int(keep_seconds * sample_rate)

    segments: list[np.ndarray] = []
    silence_start: int | None = None

    i = 0
    while i < len(energy):
        end = min(i + frame_size, len(energy))
        frame_energy = float(energy[i:end].mean())

        if frame_energy < silence_threshold:
            if silence_start is None:
                silence_start = i
        else:
            if silence_start is not None:
                gap_samples = i - silence_start
                if gap_samples > int(max_silence_seconds * sample_rate):
                    # Long silence — keep only a short portion
                    segments.append(audio[silence_start : silence_start + keep_frames])
                else:
                    # Short silence — keep as-is
                    segments.append(audio[silence_start:i])
                silence_start = None
            segments.append(audio[i:end])

        i = end

    # Handle trailing silence
    if silence_start is not None:
        gap_samples = len(audio) - silence_start
        if gap_samples > int(max_silence_seconds * sample_rate):
            segments.append(audio[silence_start : silence_start + keep_frames])
        else:
            segments.append(audio[silence_start:])

    if not segments:
        return audio
    return np.concatenate(segments, axis=0)


def reset_audio_backend() -> None:
    """Re-initialize PortAudio to rediscover devices after sleep/wake.

    Uses private sounddevice APIs (sd._terminate/_initialize) because there
    is no public reset method. If sounddevice removes these in a future
    version, this will need to be replaced with a full module reimport.
    """
    try:
        sd._terminate()
        sd._initialize()
    except Exception as exc:
        print(f"[recorder] audio backend reset failed: {exc}")


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
        self._combined_cache: np.ndarray | None = None
        self._combined_chunk_count = 0
        self._last_callback_time = 0.0
        self._stream_errors = 0

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
            self._stream_errors += 1

        with self._lock:
            if not self._recording:
                return
            self._chunks.append(indata.copy())
            self._sample_count += frames
            self._last_callback_time = time.monotonic()
            # Track peak amplitude for level metering
            self._peak = max(self._peak, float(np.abs(indata).max()))

    def start(self) -> bool:
        with self._lock:
            if self._recording:
                return False

            self._chunks = []
            self._sample_count = 0
            self._started_at = time.monotonic()
            self._last_callback_time = time.monotonic()
            self._stream_errors = 0
            self._recording = True
            self._combined_cache = None
            self._combined_chunk_count = 0

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

    @property
    def seconds_since_last_callback(self) -> float:
        """Seconds since the last audio callback. 0.0 if not recording."""
        with self._lock:
            if not self._recording or self._last_callback_time == 0.0:
                return 0.0
            return time.monotonic() - self._last_callback_time

    def restart_stream(self) -> bool:
        """Close and reopen the audio stream while preserving recorded chunks.

        Use this when the stream stops delivering callbacks (e.g. after a
        device power-management hiccup or PortAudio xrun).  Returns True
        if the stream was successfully restarted.
        """
        with self._lock:
            if not self._recording:
                return False

            # Close the dead stream
            old_stream = self._stream
            self._stream = None

        if old_stream is not None:
            try:
                old_stream.stop()
                old_stream.close()
            except Exception:
                pass

        # Reset PortAudio to rediscover devices
        reset_audio_backend()

        with self._lock:
            if not self._recording:
                return False
            try:
                self._stream = sd.InputStream(
                    device=self.device,
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype=self.dtype,
                    callback=self._callback,
                )
                self._stream.start()
                self._stream_errors = 0
                print("[recorder] stream restarted successfully")
                return True
            except Exception as exc:
                print(f"[recorder] stream restart failed: {exc}")
                return False

    def get_accumulated_audio(self) -> bytes | None:
        """Snapshot accumulated audio as FLAC bytes without stopping recording."""
        with self._lock:
            if not self._recording or not self._chunks:
                return None
            audio = self._snapshot_audio_locked()

        buffer = io.BytesIO()
        sf.write(buffer, audio, self.sample_rate, format="FLAC")
        return buffer.getvalue()

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
            audio: np.ndarray | None = None
            if chunks:
                audio = self._snapshot_audio_locked()
            self._chunks = []
            self._combined_cache = None
            self._combined_chunk_count = 0

        if not chunks or audio is None:
            return None

        # Collapse long silences so Whisper doesn't lose context after pauses
        audio = strip_long_silence(audio, self.sample_rate)
        effective_sample_count = int(audio.shape[0])

        buffer = io.BytesIO()
        sf.write(buffer, audio, self.sample_rate, format="FLAC")

        return RecordingResult(
            audio_bytes=buffer.getvalue(),
            duration_seconds=effective_sample_count / float(self.sample_rate),
            sample_count=effective_sample_count,
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

    def _snapshot_audio_locked(self) -> np.ndarray:
        """Return concatenated audio for current chunks. Caller must hold _lock.

        Uses incremental caching: only concatenates new chunks since the last
        snapshot, avoiding O(n²) re-concatenation during repeated preview polls.
        """
        if self._combined_cache is None:
            self._combined_cache = np.concatenate(self._chunks, axis=0)
            self._combined_chunk_count = len(self._chunks)
        elif self._combined_chunk_count < len(self._chunks):
            new_parts = self._chunks[self._combined_chunk_count:]
            if new_parts:
                appended = np.concatenate(new_parts, axis=0)
                self._combined_cache = np.concatenate((self._combined_cache, appended), axis=0)
                self._combined_chunk_count = len(self._chunks)

        # Return a copy so callers can safely use it outside the lock.
        return self._combined_cache.copy()
