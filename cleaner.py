"""Post-transcription cleanup via regex-based filler removal."""

from __future__ import annotations

import re


# Filler patterns, ordered from multi-word to single-word
_FILLER_PATTERNS = [
    # Multi-word fillers (must come first)
    r"\byou know what I mean\b",
    r"\byou know what\b",
    r"\byou know\b",
    r"\bI mean\b",
    r"\bsort of\b",
    r"\bkind of\b",
    r"\bor something like that\b",
    r"\bor something\b",
    r"\bor whatever\b",
    r"\band stuff like that\b",
    r"\band stuff\b",
    r"\bat the end of the day\b",
    # Single-word fillers (word boundaries prevent matching inside words)
    r"\buh\b",
    r"\bum\b",
    r"\bah\b",
    r"\berm\b",
    r"\ber\b",
    r"\bhmm\b",
    r"\bhm\b",
    r"\bbasically\b",
    r"\bliterally\b",
    r"\bactually\b",
]

_FILLER_RE = re.compile(
    "|".join(f"(?:{p})" for p in _FILLER_PATTERNS),
    re.IGNORECASE,
)

# Repeated words: "I I think", "the the", "we we should"
_REPEATED_WORD_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)

# Cleanup artifacts: multiple spaces, space before punctuation, leading/trailing commas
_MULTI_SPACE_RE = re.compile(r"  +")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,!?;:])")
_LEADING_COMMA_RE = re.compile(r"^\s*,\s*", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",\s*$", re.MULTILINE)
_COMMA_COMMA_RE = re.compile(r",\s*,")


class TextCleaner:
    """Remove filler words and clean up transcription artifacts using regex."""

    def __init__(self, **_kwargs) -> None:
        # Accept and ignore kwargs for backward compat with config loading
        pass

    def health_check(self) -> bool:
        return True

    def prewarm(self, **_kwargs) -> bool:
        return True

    @property
    def enabled(self) -> bool:
        return True

    @enabled.setter
    def enabled(self, _value: bool) -> None:
        pass

    def clean(self, text: str) -> str:
        if not text.strip():
            return text

        result = text

        # Remove filler words/phrases
        result = _FILLER_RE.sub("", result)

        # Remove repeated words ("I I think" -> "I think")
        result = _REPEATED_WORD_RE.sub(r"\1", result)

        # Clean up punctuation artifacts
        result = _COMMA_COMMA_RE.sub(",", result)
        result = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", result)
        result = _LEADING_COMMA_RE.sub("", result)
        result = _TRAILING_COMMA_RE.sub("", result)
        result = _MULTI_SPACE_RE.sub(" ", result)
        result = result.strip()

        # Fix capitalization after cleanup
        if result:
            result = result[0].upper() + result[1:]

        return result if result else text

    def close(self) -> None:
        pass
