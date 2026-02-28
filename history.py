"""Transcription history — keeps the last N transcriptions in memory."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass
class HistoryEntry:
    text: str
    timestamp: float  # time.time()
    language: str
    duration_seconds: float


class TranscriptionHistory:
    def __init__(self, max_items: int = 50) -> None:
        self._entries: deque[HistoryEntry] = deque(maxlen=max_items)

    def add(self, text: str, language: str, duration_seconds: float) -> None:
        self._entries.append(HistoryEntry(
            text=text,
            timestamp=time.time(),
            language=language,
            duration_seconds=duration_seconds,
        ))

    def entries(self) -> list[HistoryEntry]:
        """Return entries newest-first."""
        return list(reversed(self._entries))

    def last(self) -> HistoryEntry | None:
        return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
