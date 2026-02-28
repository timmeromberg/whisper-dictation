"""Whisper transcription clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlsplit

import httpx


DEFAULT_LOCAL_URL = "http://localhost:2022/v1/audio/transcriptions"
DEFAULT_LOCAL_MODEL = "large-v3"
DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
DEFAULT_GROQ_MODEL = "whisper-large-v3"


class WhisperTranscriber(ABC):
    """Base interface for OpenAI-compatible Whisper transcription clients."""

    @abstractmethod
    def health_check(self) -> bool:
        """Return True when the configured service is reachable."""

    @abstractmethod
    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe in-memory WAV audio bytes."""

    @abstractmethod
    def close(self) -> None:
        """Release HTTP resources."""


class _HTTPWhisperTranscriber(WhisperTranscriber):
    """Shared HTTP implementation for OpenAI-compatible transcription endpoints."""

    def __init__(
        self,
        url: str,
        language: str,
        model: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.language = language
        self.model = model
        self._client = httpx.Client(timeout=timeout_seconds, headers=headers or {})

    def health_check(self) -> bool:
        parts = urlsplit(self.url)
        if not parts.scheme or not parts.netloc:
            return False

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
        data: dict[str, str] = {
            "model": self.model,
        }
        if self.language and self.language != "auto":
            data["language"] = self.language

        response = self._client.post(self.url, data=data, files=files)
        response.raise_for_status()

        payload = response.json()
        return str(payload.get("text", "")).strip()

    def close(self) -> None:
        self._client.close()


class LocalWhisperTranscriber(_HTTPWhisperTranscriber):
    """Transcriber for local whisper.cpp OpenAI-compatible servers."""

    def __init__(
        self,
        url: str = DEFAULT_LOCAL_URL,
        language: str = "en",
        model: str = DEFAULT_LOCAL_MODEL,
        timeout_seconds: float = 120.0,
    ) -> None:
        super().__init__(
            url=url,
            language=language,
            model=model,
            timeout_seconds=timeout_seconds,
        )


class GroqWhisperTranscriber(_HTTPWhisperTranscriber):
    """Transcriber for the Groq OpenAI-compatible Whisper API."""

    def __init__(
        self,
        api_key: str,
        url: str = DEFAULT_GROQ_URL,
        language: str = "en",
        model: str = DEFAULT_GROQ_MODEL,
        timeout_seconds: float = 120.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key.strip():
            headers["Authorization"] = f"Bearer {api_key.strip()}"

        super().__init__(
            url=url,
            language=language,
            model=model,
            timeout_seconds=timeout_seconds,
            headers=headers,
        )


def create_transcriber(config: Any) -> WhisperTranscriber:
    """Build a provider-specific transcriber from whisper config."""

    provider = str(getattr(config, "provider", "local")).strip().lower()
    language = str(getattr(config, "language", "en"))
    timeout_seconds = float(getattr(config, "timeout_seconds", 120.0))

    if provider == "local":
        local_cfg = getattr(config, "local", None)
        url = str(getattr(local_cfg, "url", DEFAULT_LOCAL_URL))
        model = str(getattr(local_cfg, "model", DEFAULT_LOCAL_MODEL))
        return LocalWhisperTranscriber(
            url=url,
            language=language,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    if provider == "groq":
        groq_cfg = getattr(config, "groq", None)
        api_key = str(getattr(groq_cfg, "api_key", ""))
        url = str(getattr(groq_cfg, "url", DEFAULT_GROQ_URL))
        model = str(getattr(groq_cfg, "model", DEFAULT_GROQ_MODEL))
        return GroqWhisperTranscriber(
            api_key=api_key,
            url=url,
            language=language,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    raise ValueError(f"Unsupported whisper provider '{provider}'. Expected 'local' or 'groq'.")
