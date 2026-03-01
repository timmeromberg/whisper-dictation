"""AI rewriting of transcriptions via Groq chat completions."""

from __future__ import annotations

import httpx

from .log import log

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class Rewriter:
    """Rewrites transcribed text using an LLM via Groq's chat completions API."""

    def __init__(self, api_key: str, model: str, prompt: str) -> None:
        self._model = model
        self._prompt = prompt
        self._client = httpx.Client(
            timeout=10.0,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            transport=httpx.HTTPTransport(retries=2),
        )

    def rewrite(self, text: str) -> str:
        """Rewrite transcribed text. Returns original text on any failure."""
        if not text.strip():
            return text

        try:
            response = self._client.post(
                GROQ_CHAT_URL,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": self._prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.3,
                },
            )
            if response.status_code != 200:
                log("rewriter", f"API error {response.status_code}: {response.text[:200]}")
                return text

            result = str(response.json()["choices"][0]["message"]["content"]).strip()
            if not result:
                return text
            return result
        except Exception as exc:
            log("rewriter", f"Rewrite failed, using original: {exc}")
            return text

    def close(self) -> None:
        self._client.close()
