"""Post-transcription cleanup via Ollama."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

SYSTEM_PROMPT = """You are a transcription cleaner. Your ONLY job is to clean up speech-to-text output.

Rules:
1. Remove filler words: uh, um, ah, er, like (when used as filler), you know, I mean, sort of, kind of, basically, actually, literally, right (when used as filler)
2. Remove false starts and repeated words
3. Fix punctuation and capitalization
4. Do NOT change the meaning, add words, or rephrase
5. Do NOT add commentary or explanation
6. Output ONLY the cleaned text, nothing else"""


class TextCleaner:
    """Wraps Ollama text generation for deterministic transcript cleanup."""

    def __init__(
        self,
        enabled: bool,
        url: str,
        model: str,
        timeout_seconds: float = 60.0,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.enabled = enabled
        self.url = url
        self.model = model
        self.system_prompt = system_prompt
        self._client = httpx.Client(timeout=timeout_seconds)

    def _base_url(self) -> str:
        parts = urlsplit(self.url)
        return f"{parts.scheme}://{parts.netloc}"

    def health_check(self) -> bool:
        if not self.enabled:
            return True

        tags_url = f"{self._base_url()}/api/tags"
        try:
            response = self._client.get(tags_url)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def prewarm(self, prompt: str = "Ready.") -> bool:
        if not self.enabled:
            return False

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

        try:
            response = self._client.post(self.url, json=payload)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def clean(self, text: str) -> str:
        if not self.enabled:
            return text

        payload = {
            "model": self.model,
            "system": self.system_prompt,
            "prompt": text,
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }

        response = self._client.post(self.url, json=payload)
        response.raise_for_status()

        response_json = response.json()
        cleaned = str(response_json.get("response", "")).strip()
        return cleaned or text

    def close(self) -> None:
        self._client.close()
