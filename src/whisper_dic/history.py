"""Transcription history — keeps the last N transcriptions in memory and optionally persists to disk."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from .log import log


def _default_persist_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "whisper-dic" / "history.json"


_DEFAULT_PERSIST_PATH = _default_persist_path()
_SAVE_DEBOUNCE_SECONDS = 5.0


@dataclass
class HistoryEntry:
    text: str
    timestamp: float  # time.time()
    language: str
    duration_seconds: float


class TranscriptionHistory:
    def __init__(self, max_items: int = 50, persist_path: Path | None = _DEFAULT_PERSIST_PATH) -> None:
        self._entries: deque[HistoryEntry] = deque(maxlen=max_items)
        self._persist_path = persist_path
        self._last_save_time: float = 0.0
        self._dirty = False

        if persist_path is not None:
            self._load()

    def _load(self) -> None:
        """Load history from disk. Graceful on missing or corrupt files."""
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                log("history", "Corrupt history file (not a list), starting fresh")
                return
            for item in raw:
                if isinstance(item, dict) and "text" in item:
                    self._entries.append(HistoryEntry(
                        text=str(item["text"]),
                        timestamp=float(item.get("timestamp", 0.0)),
                        language=str(item.get("language", "en")),
                        duration_seconds=float(item.get("duration_seconds", 0.0)),
                    ))
            log("history", f"Loaded {len(self._entries)} entries from disk")
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            log("history", f"Failed to load history: {exc}")

    def _save(self, force: bool = False) -> None:
        """Save history to disk, debounced unless force=True."""
        if self._persist_path is None:
            return
        if not force and not self._dirty:
            return
        now = time.monotonic()
        if not force and (now - self._last_save_time) < _SAVE_DEBOUNCE_SECONDS:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(e) for e in self._entries]
            content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            # Write to temp file with restrictive permissions, then atomic-replace.
            # Prevents a window where the file is world-readable before chmod.
            import tempfile
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self._persist_path.parent),
                prefix=f".{self._persist_path.name}.",
                suffix=".tmp",
            )
            tmp_path = Path(tmp_name)
            try:
                os.chmod(fd, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self._persist_path)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
            self._last_save_time = now
            self._dirty = False
        except OSError as exc:
            log("history", f"Failed to save history: {exc}")

    def add(self, text: str, language: str, duration_seconds: float) -> None:
        self._entries.append(HistoryEntry(
            text=text,
            timestamp=time.time(),
            language=language,
            duration_seconds=duration_seconds,
        ))
        self._dirty = True
        self._save()

    def entries(self) -> list[HistoryEntry]:
        """Return entries newest-first."""
        return list(reversed(self._entries))

    def last(self) -> HistoryEntry | None:
        return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        self._entries.clear()
        self._dirty = True
        self._save(force=True)

    def flush(self) -> None:
        """Force-save pending changes. Call on shutdown."""
        if self._dirty:
            self._save(force=True)

    def __len__(self) -> int:
        return len(self._entries)
