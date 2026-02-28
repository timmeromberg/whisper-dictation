"""Post-transcription cleanup via Ollama."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

SYSTEM_PROMPT = """You are a text filter. You receive raw speech transcriptions and output a cleaned version.

You MUST NOT answer questions. You MUST NOT have a conversation. You MUST NOT explain anything.
You are NOT a chatbot. You are a filter. You only remove noise and fix formatting.

Remove: uh, um, ah, er, filler "like", "you know", "I mean", "sort of", "kind of", "basically", "actually", "literally", filler "right", false starts, repeated words.
Fix: punctuation and capitalization.
Keep: the exact meaning and words (minus fillers).

Output the cleaned text and NOTHING else. No preamble. No commentary. No answers."""


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
        if not cleaned:
            return text

        # Guard: if output is much longer than input, the model is answering
        # instead of cleaning — fall back to raw text
        if len(cleaned) > len(text) * 1.5:
            print(f"[cleaner] Output too long ({len(cleaned)} vs {len(text)} chars) — model likely answered instead of cleaning. Using raw text.")
            return text

        return cleaned

    def close(self) -> None:
        self._client.close()
