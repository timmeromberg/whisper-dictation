"""Shared fixtures for whisper-dic tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tmp_config(tmp_path: Path) -> Path:
    """Minimal valid TOML config in a temp directory."""
    p = tmp_path / "config.toml"
    p.write_text('[hotkey]\nkey = "left_option"\n')
    return p


@pytest.fixture()
def example_config() -> Path:
    """Path to the real config.example.toml shipped with the project."""
    return Path(__file__).resolve().parent.parent / "config.example.toml"
