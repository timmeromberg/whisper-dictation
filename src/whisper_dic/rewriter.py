"""AI rewriting of transcriptions via Groq chat completions."""

from __future__ import annotations

import re

import httpx

from .log import log

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

# (description, system prompt)
REWRITE_PRESETS: dict[str, tuple[str, str]] = {
    "light": (
        "Fix punctuation and capitalization only",
        "You are a dictation assistant. Fix only punctuation and capitalization in the "
        "following transcription. Do not change any words, phrasing, or sentence structure. "
        "Return only the corrected text, nothing else.",
    ),
    "medium": (
        "Fix grammar, punctuation, keep original words",
        "You are a dictation assistant. Fix grammar, punctuation, and capitalization in the "
        "following transcription. Keep the original words and meaning as much as possible. "
        "Return only the corrected text, nothing else.",
    ),
    "full": (
        "Reshape into polished prose",
        "You are a dictation assistant. Rewrite the following transcription into clear, "
        "polished prose. Fix grammar, improve sentence structure, and remove redundancy "
        "while preserving the original meaning. Return only the rewritten text, nothing else.",
    ),
}

REWRITE_MODES = list(REWRITE_PRESETS.keys()) + ["custom"]


def _redact_sensitive(text: str) -> str:
    return re.sub(r"(gsk_|sk-|Bearer\s+)\S{6,}", r"\1***", text)


def prompt_for_mode(mode: str, custom_prompt: str) -> str:
    """Return the system prompt for a given rewrite mode."""
    if mode in REWRITE_PRESETS:
        return REWRITE_PRESETS[mode][1]
    return custom_prompt


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
                log("rewriter", f"API error {response.status_code}: {_redact_sensitive(response.text[:200])}")
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
