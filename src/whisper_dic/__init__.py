"""whisper-dic — voice-to-text dictation tool."""

from __future__ import annotations

from importlib.resources import files

__version__: str = files("whisper_dic").joinpath("VERSION").read_text().strip()
