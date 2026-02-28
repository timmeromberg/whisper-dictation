"""Timestamped logging for whisper-dic."""

from __future__ import annotations

import time

_start = time.monotonic()


def log(tag: str, message: str) -> None:
    """Print a timestamped log line: [HH:MM:SS.mmm][tag] message"""
    elapsed = time.monotonic() - _start
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = elapsed % 60
    ts = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
    print(f"[{ts}][{tag}] {message}", flush=True)
