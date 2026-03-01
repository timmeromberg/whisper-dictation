"""Tests for TranscriptionHistory."""

from __future__ import annotations

import json
from pathlib import Path

from whisper_dic.history import TranscriptionHistory


class TestHistory:
    def test_add_and_entries(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        h.add("hello", "en", 1.5)
        assert len(h) == 1
        assert h.entries()[0].text == "hello"

    def test_newest_first(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        h.add("first", "en", 1.0)
        h.add("second", "en", 2.0)
        entries = h.entries()
        assert entries[0].text == "second"
        assert entries[1].text == "first"

    def test_last(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        assert h.last() is None
        h.add("hello", "en", 1.0)
        assert h.last() is not None
        assert h.last().text == "hello"

    def test_clear(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        h.add("hello", "en", 1.0)
        h.clear()
        assert len(h) == 0
        assert h.last() is None

    def test_maxlen_overflow(self) -> None:
        h = TranscriptionHistory(max_items=3, persist_path=None)
        for i in range(5):
            h.add(f"entry {i}", "en", 1.0)
        assert len(h) == 3
        # Oldest entries should be gone
        texts = [e.text for e in h.entries()]
        assert "entry 0" not in texts
        assert "entry 4" in texts

    def test_empty_history(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        assert len(h) == 0
        assert h.entries() == []
        assert h.last() is None

    def test_entry_fields(self) -> None:
        h = TranscriptionHistory(persist_path=None)
        h.add("test", "nl", 3.14)
        entry = h.last()
        assert entry.text == "test"
        assert entry.language == "nl"
        assert entry.duration_seconds == 3.14
        assert entry.timestamp > 0


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        h1 = TranscriptionHistory(persist_path=path)
        h1.add("hello", "en", 1.5)
        h1.add("world", "nl", 2.0)
        h1.flush()

        assert path.exists()

        h2 = TranscriptionHistory(persist_path=path)
        assert len(h2) == 2
        assert h2.entries()[0].text == "world"
        assert h2.entries()[1].text == "hello"

    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        h = TranscriptionHistory(persist_path=path)
        assert len(h) == 0

    def test_corrupt_json_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not valid json!!!")
        h = TranscriptionHistory(persist_path=path)
        assert len(h) == 0

    def test_non_list_json_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "obj.json"
        path.write_text('{"key": "value"}')
        h = TranscriptionHistory(persist_path=path)
        assert len(h) == 0

    def test_clear_persists(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        h = TranscriptionHistory(persist_path=path)
        h.add("hello", "en", 1.0)
        h.flush()
        h.clear()

        h2 = TranscriptionHistory(persist_path=path)
        assert len(h2) == 0

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "history.json"
        h = TranscriptionHistory(persist_path=path)
        h.add("hello", "en", 1.0)
        h.flush()
        assert path.exists()

    def test_flush_when_not_dirty_is_noop(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        h = TranscriptionHistory(persist_path=path)
        h.flush()
        assert not path.exists()

    def test_maxlen_respected_on_load(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        # Write more entries than maxlen
        data = [{"text": f"entry {i}", "timestamp": i, "language": "en", "duration_seconds": 1.0} for i in range(10)]
        path.write_text(json.dumps(data))
        h = TranscriptionHistory(max_items=5, persist_path=path)
        # deque maxlen keeps last 5 appended (entries 5-9)
        assert len(h) == 5
        assert h.entries()[0].text == "entry 9"
