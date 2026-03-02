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

# Default per-category system prompts for context-aware rewriting
CONTEXT_PROMPTS: dict[str, str] = {
    "coding": (
        "You are a dictation assistant for software developers. The user is dictating "
        "into a code editor or terminal — likely writing AI prompts, code instructions, "
        "commit messages, or technical documentation.\n\n"
        "Rules:\n"
        "- Preserve all technical terms, file names, function names, and variable names exactly\n"
        "- Convert spoken code patterns to symbols: 'dot py' → '.py', 'dash dash' → '--', "
        "'equals equals' → '==', 'dot' → '.', 'slash' → '/', 'underscore' → '_', "
        "'hash' or 'pound' → '#', 'at sign' → '@', 'pipe' → '|', 'tilde' → '~', "
        "'backtick' → '`', 'ampersand' → '&', 'caret' → '^', 'star' or 'asterisk' → '*'\n"
        "- Keep the user's full message — do not shorten, summarize, or remove detail\n"
        "- Preserve questions as questions — if the user asks something, keep the question mark\n"
        "- Fix grammar and punctuation only — do not rephrase or restructure sentences\n"
        "- Remove only speech artifacts (um, uh, false starts) — keep all intentional content\n"
        "- Return only the corrected text, nothing else."
    ),
    "chat": (
        "You are a dictation assistant. The user is sending a casual message in a chat "
        "app (Slack, Discord, iMessage, etc.).\n\n"
        "Rules:\n"
        "- Keep it short and conversational\n"
        "- Fix obvious grammar mistakes but preserve informal tone\n"
        "- Do not make the message sound overly formal or wordy\n"
        "- Preserve slang, abbreviations, and casual phrasing\n"
        "- Return only the corrected text, nothing else."
    ),
    "email": (
        "You are a dictation assistant. The user is composing an email.\n\n"
        "Rules:\n"
        "- Use professional, clear language\n"
        "- Fix grammar, punctuation, and sentence structure\n"
        "- Maintain a polite and professional tone\n"
        "- Do not add greetings or sign-offs unless the user dictated them\n"
        "- Return only the corrected text, nothing else."
    ),
    "writing": (
        "You are a dictation assistant. The user is writing notes, documentation, or "
        "prose in an app like Notion, Obsidian, or Apple Notes.\n\n"
        "Rules:\n"
        "- Improve clarity, flow, and sentence structure\n"
        "- Fix grammar and punctuation thoroughly\n"
        "- Remove verbal filler and false starts\n"
        "- Preserve the original meaning and structure\n"
        "- Return only the rewritten text, nothing else."
    ),
    "browser": (
        "You are a dictation assistant. The user is typing into a web browser — it "
        "could be a form, search bar, social media post, or web app.\n\n"
        "Rules:\n"
        "- Fix grammar, punctuation, and capitalization\n"
        "- Keep the original words and meaning as much as possible\n"
        "- Use a balanced, neutral tone\n"
        "- Return only the corrected text, nothing else."
    ),
}


def _redact_sensitive(text: str) -> str:
    return re.sub(r"(gsk_|sk-|Bearer\s+)\S{6,}", r"\1***", text)


def prompt_for_mode(mode: str, custom_prompt: str) -> str:
    """Return the system prompt for a given rewrite mode."""
    if mode in REWRITE_PRESETS:
        return REWRITE_PRESETS[mode][1]
    return custom_prompt


def prompt_for_context(
    category: str | None,
    context_prompt: str,
    global_mode: str,
    global_custom_prompt: str,
) -> str:
    """Resolve the effective system prompt for a rewrite context.

    If a category is set and has a non-empty custom prompt, use it.
    If a category is set but prompt is empty, use the built-in default for that category.
    If no category (None), fall back to the global mode/prompt.
    """
    if category is not None:
        if context_prompt:
            return context_prompt
        return CONTEXT_PROMPTS.get(category, prompt_for_mode(global_mode, global_custom_prompt))
    return prompt_for_mode(global_mode, global_custom_prompt)


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

    def rewrite(self, text: str, prompt_override: str | None = None) -> str:
        """Rewrite transcribed text. Returns original text on any failure.

        Args:
            text: The transcribed text to rewrite.
            prompt_override: If provided, uses this system prompt instead of the default.
        """
        if not text.strip():
            return text

        effective_prompt = prompt_override if prompt_override else self._prompt

        try:
            response = self._client.post(
                GROQ_CHAT_URL,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": effective_prompt},
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
        except httpx.TimeoutException as exc:
            log("rewriter", f"Rewrite timed out, using original: {exc}")
            return text
        except httpx.HTTPStatusError as exc:
            log("rewriter", f"Rewrite HTTP error {exc.response.status_code}, using original")
            return text
        except Exception as exc:
            log("rewriter", f"Rewrite failed, using original: {exc}")
            return text

    def close(self) -> None:
        self._client.close()
