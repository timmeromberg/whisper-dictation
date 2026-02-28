"""Tests for TranscriptionHistory."""

from __future__ import annotations

from history import TranscriptionHistory


class TestHistory:
    def test_add_and_entries(self) -> None:
        h = TranscriptionHistory()
        h.add("hello", "en", 1.5)
        assert len(h) == 1
        assert h.entries()[0].text == "hello"

    def test_newest_first(self) -> None:
        h = TranscriptionHistory()
        h.add("first", "en", 1.0)
        h.add("second", "en", 2.0)
        entries = h.entries()
        assert entries[0].text == "second"
        assert entries[1].text == "first"

    def test_last(self) -> None:
        h = TranscriptionHistory()
        assert h.last() is None
        h.add("hello", "en", 1.0)
        assert h.last() is not None
        assert h.last().text == "hello"

    def test_clear(self) -> None:
        h = TranscriptionHistory()
        h.add("hello", "en", 1.0)
        h.clear()
        assert len(h) == 0
        assert h.last() is None

    def test_maxlen_overflow(self) -> None:
        h = TranscriptionHistory(max_items=3)
        for i in range(5):
            h.add(f"entry {i}", "en", 1.0)
        assert len(h) == 3
        # Oldest entries should be gone
        texts = [e.text for e in h.entries()]
        assert "entry 0" not in texts
        assert "entry 4" in texts

    def test_empty_history(self) -> None:
        h = TranscriptionHistory()
        assert len(h) == 0
        assert h.entries() == []
        assert h.last() is None

    def test_entry_fields(self) -> None:
        h = TranscriptionHistory()
        h.add("test", "nl", 3.14)
        entry = h.last()
        assert entry.text == "test"
        assert entry.language == "nl"
        assert entry.duration_seconds == 3.14
        assert entry.timestamp > 0
