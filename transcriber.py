"""Whisper transcription client."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class WhisperTranscriber:
    """Send WAV audio to an OpenAI-compatible Whisper transcription endpoint."""

    def __init__(
        self,
        url: str,
        language: str = "en",
        model: str = "large-v3",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.url = url
        self.language = language
        self.model = model
        self._client = httpx.Client(timeout=timeout_seconds)

    def health_check(self) -> bool:
        parts = urlsplit(self.url)
        root_url = f"{parts.scheme}://{parts.netloc}/"
        try:
            self._client.get(root_url)
            return True
        except httpx.HTTPError:
            return False

    def transcribe(self, wav_bytes: bytes) -> str:
        files = {
            "file": ("dictation.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "model": self.model,
            "language": self.language,
        }

        response = self._client.post(self.url, data=data, files=files)
        response.raise_for_status()

        payload = response.json()
        return str(payload.get("text", "")).strip()

    def close(self) -> None:
        self._client.close()
