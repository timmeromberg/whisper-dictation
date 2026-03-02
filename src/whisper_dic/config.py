"""Configuration loading, persistence, and live-reloading for whisper-dic."""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .audio_control import AudioControlConfig
from .log import log

LANG_NAMES = {
    "en": "English", "nl": "Dutch", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "auto": "Auto-detect",
    "ar": "Arabic", "hi": "Hindi", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian", "da": "Danish", "no": "Norwegian",
}


@dataclass
class HotkeyConfig:
    key: str = "left_option"


@dataclass
class RecordingConfig:
    min_duration: float = 0.3
    max_duration: float = 300.0
    sample_rate: int = 16000
    device: str | None = None
    streaming_preview: bool = False
    preview_interval: float = 3.0
    preview_provider: str = ""


@dataclass
class WhisperLocalConfig:
    url: str = "http://localhost:2022/v1/audio/transcriptions"
    model: str = "large-v3"


@dataclass
class WhisperGroqConfig:
    api_key: str = ""
    model: str = "whisper-large-v3"
    url: str = "https://api.groq.com/openai/v1/audio/transcriptions"


@dataclass
class WhisperConfig:
    provider: str = "local"
    language: str = "en"
    languages: list[str] = field(default_factory=lambda: ["en"])
    timeout_seconds: float = 120.0
    prompt: str = ""
    failover: bool = False
    local: WhisperLocalConfig = field(default_factory=WhisperLocalConfig)
    groq: WhisperGroqConfig = field(default_factory=WhisperGroqConfig)


@dataclass
class PasteConfig:
    auto_send: bool = False


@dataclass
class TextCommandsConfig:
    enabled: bool = True


@dataclass
class AudioFeedbackConfig:
    enabled: bool = True
    start_frequency: float = 880.0
    stop_frequency: float = 660.0
    duration_seconds: float = 0.08
    volume: float = 0.2


@dataclass
class ContextConfig:
    """Per-category rewrite context configuration."""

    enabled: bool = True
    prompt: str = ""


@dataclass
class RewriteConfig:
    enabled: bool = False
    mode: str = "light"
    model: str = "llama-3.3-70b-versatile"
    prompt: str = ""  # only used when mode = "custom"
    contexts: dict[str, ContextConfig] = field(default_factory=dict)


@dataclass
class OverlayConfig:
    reduced_motion: bool = False
    high_contrast: bool = False
    font_scale: float = 1.0


@dataclass
class AppConfig:
    hotkey: HotkeyConfig
    recording: RecordingConfig
    paste: PasteConfig
    text_commands: TextCommandsConfig
    whisper: WhisperConfig
    audio_feedback: AudioFeedbackConfig
    audio_control: AudioControlConfig = field(default_factory=AudioControlConfig)
    rewrite: RewriteConfig = field(default_factory=RewriteConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    custom_commands: dict[str, str] = field(default_factory=dict)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    cursor: Any = data
    for part in name.split("."):
        if not isinstance(cursor, dict):
            return {}
        cursor = cursor.get(part, {})
    return cursor if isinstance(cursor, dict) else {}


_CONTEXT_CATEGORIES = ("coding", "chat", "email", "writing", "browser")


def _parse_contexts(contexts_data: dict[str, Any]) -> dict[str, ContextConfig]:
    """Parse [rewrite.contexts.*] sections. Missing categories get defaults."""
    contexts: dict[str, ContextConfig] = {}
    for cat in _CONTEXT_CATEGORIES:
        cat_data = contexts_data.get(cat, {})
        if isinstance(cat_data, dict):
            contexts[cat] = ContextConfig(
                enabled=bool(cat_data.get("enabled", True)),
                prompt=str(cat_data.get("prompt", "")),
            )
        else:
            contexts[cat] = ContextConfig()
    return contexts


def load_config(path: Path) -> AppConfig:
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    hotkey_data = _section(data, "hotkey")
    recording_data = _section(data, "recording")
    paste_data = _section(data, "paste")
    text_commands_data = _section(data, "text_commands")
    whisper_data = _section(data, "whisper")
    whisper_local_data = _section(data, "whisper.local")
    whisper_groq_data = _section(data, "whisper.groq")
    feedback_data = _section(data, "audio_feedback")
    audio_control_data = _section(data, "audio_control")
    rewrite_data = _section(data, "rewrite")
    contexts_data = _section(data, "rewrite.contexts")
    overlay_data = _section(data, "overlay")
    custom_commands_data = _section(data, "custom_commands")

    provider = str(whisper_data.get("provider", "local")).strip().lower()
    if provider not in {"local", "groq"}:
        provider = "local"

    raw_languages = whisper_data.get("languages", None)
    language = str(whisper_data.get("language", "en"))
    if isinstance(raw_languages, list) and raw_languages:
        languages = [str(lang) for lang in raw_languages]
    else:
        languages = [language]
    if language not in languages:
        languages.insert(0, language)

    config = AppConfig(
        hotkey=HotkeyConfig(
            key=str(hotkey_data.get("key", "left_option")),
        ),
        recording=RecordingConfig(
            min_duration=float(recording_data.get("min_duration", 0.3)),
            max_duration=float(recording_data.get("max_duration", 300.0)),
            sample_rate=int(recording_data.get("sample_rate", 16000)),
            device=recording_data.get("device", None) or None,
            streaming_preview=bool(recording_data.get("streaming_preview", False)),
            preview_interval=float(recording_data.get("preview_interval", 3.0)),
            preview_provider=str(recording_data.get("preview_provider", "")),
        ),
        paste=PasteConfig(
            auto_send=bool(paste_data.get("auto_send", False)),
        ),
        text_commands=TextCommandsConfig(
            enabled=bool(text_commands_data.get("enabled", True)),
        ),
        whisper=WhisperConfig(
            provider=provider,
            language=language,
            languages=languages,
            timeout_seconds=float(whisper_data.get("timeout_seconds", 120.0)),
            prompt=str(whisper_data.get("prompt", "")),
            failover=bool(whisper_data.get("failover", False)),
            local=WhisperLocalConfig(
                url=str(
                    whisper_local_data.get(
                        "url",
                        "http://localhost:2022/v1/audio/transcriptions",
                    )
                ),
                model=str(whisper_local_data.get("model", "large-v3")),
            ),
            groq=WhisperGroqConfig(
                api_key=str(whisper_groq_data.get("api_key", "")),
                model=str(whisper_groq_data.get("model", "whisper-large-v3")),
                url=str(
                    whisper_groq_data.get(
                        "url",
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                    )
                ),
            ),
        ),
        audio_feedback=AudioFeedbackConfig(
            enabled=bool(feedback_data.get("enabled", True)),
            start_frequency=float(feedback_data.get("start_frequency", 880.0)),
            stop_frequency=float(feedback_data.get("stop_frequency", 660.0)),
            duration_seconds=float(feedback_data.get("duration_seconds", 0.08)),
            volume=float(feedback_data.get("volume", 0.2)),
        ),
        audio_control=AudioControlConfig(
            enabled=bool(audio_control_data.get("enabled", False)),
            mute_local=bool(audio_control_data.get("mute_local", True)),
            devices=list(audio_control_data.get("devices", [])),
        ),
        rewrite=RewriteConfig(
            enabled=bool(rewrite_data.get("enabled", False)),
            mode=str(rewrite_data.get("mode", "light")),
            model=str(rewrite_data.get("model", "llama-3.3-70b-versatile")),
            prompt=str(rewrite_data.get("prompt", "")),
            contexts=_parse_contexts(contexts_data),
        ),
        overlay=OverlayConfig(
            reduced_motion=bool(overlay_data.get("reduced_motion", False)),
            high_contrast=bool(overlay_data.get("high_contrast", False)),
            font_scale=float(overlay_data.get("font_scale", 1.0)),
        ),
        custom_commands={str(k): str(v) for k, v in custom_commands_data.items()},
    )
    return _validate_config(config)


def _validate_config(config: AppConfig) -> AppConfig:
    """Clamp config values to sane ranges. Logs warnings, never crashes."""
    if config.recording.min_duration <= 0:
        log("config", f"min_duration={config.recording.min_duration} invalid, clamped to 0.1")
        config.recording.min_duration = 0.1

    if config.recording.max_duration <= config.recording.min_duration:
        log("config", f"max_duration={config.recording.max_duration} invalid, clamped to 300.0")
        config.recording.max_duration = 300.0

    valid_rates = {8000, 16000, 22050, 44100, 48000}
    if config.recording.sample_rate not in valid_rates:
        log("config", f"sample_rate={config.recording.sample_rate} invalid, clamped to 16000")
        config.recording.sample_rate = 16000

    if not 0.1 <= config.recording.preview_interval <= 30.0:
        clamped = max(0.1, min(30.0, config.recording.preview_interval))
        log("config", f"preview_interval={config.recording.preview_interval} out of range, clamped to {clamped}")
        config.recording.preview_interval = clamped

    if config.recording.preview_provider and config.recording.preview_provider not in {"local", "groq"}:
        log("config", f"preview_provider='{config.recording.preview_provider}' invalid, clearing")
        config.recording.preview_provider = ""

    if not 0.0 <= config.audio_feedback.volume <= 1.0:
        clamped = max(0.0, min(1.0, config.audio_feedback.volume))
        log("config", f"volume={config.audio_feedback.volume} out of range, clamped to {clamped}")
        config.audio_feedback.volume = clamped

    if not 0.75 <= config.overlay.font_scale <= 2.0:
        clamped = max(0.75, min(2.0, config.overlay.font_scale))
        log("config", f"overlay.font_scale={config.overlay.font_scale} out of range, clamped to {clamped}")
        config.overlay.font_scale = clamped

    if not config.whisper.language:
        log("config", "language is empty, defaulting to 'en'")
        config.whisper.language = "en"

    if config.whisper.provider not in {"local", "groq"}:
        log("config", f"provider='{config.whisper.provider}' invalid, defaulting to 'local'")
        config.whisper.provider = "local"

    if config.whisper.timeout_seconds <= 0:
        log("config", f"timeout_seconds={config.whisper.timeout_seconds} invalid, clamped to 120.0")
        config.whisper.timeout_seconds = 120.0

    return config


def _to_toml_literal(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return '""'

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value

    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered

    if re.fullmatch(r"[+-]?\d+", value):
        return str(int(value))

    float_like = re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?", value)
    sci_like = re.fullmatch(r"[+-]?\d+[eE][+-]?\d+", value)
    if float_like or sci_like:
        try:
            float(value)
            return value
        except ValueError:
            pass

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _find_section_span(text: str, section: str) -> tuple[int, int] | None:
    header_re = re.compile(rf"(?m)^\[{re.escape(section)}\]\s*$")
    header_match = header_re.search(text)
    if header_match is None:
        return None

    body_start = header_match.end()
    next_header = re.compile(r"(?m)^\[[^\]\n]+\]\s*$").search(text, body_start)
    body_end = next_header.start() if next_header else len(text)
    return body_start, body_end


def _set_key_in_block(block: str, key: str, value_literal: str) -> str:
    key_re = re.compile(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$")
    key_match = key_re.search(block)
    if key_match is not None:
        return (
            block[: key_match.start()]
            + f"{key_match.group(1)}{value_literal}"
            + block[key_match.end() :]
        )

    trailing_ws = re.search(r"[ \t\r\n]*\Z", block)
    insert_at = trailing_ws.start() if trailing_ws is not None else len(block)
    prefix = block[:insert_at]
    suffix = block[insert_at:]

    if prefix and not prefix.endswith("\n"):
        prefix += "\n"

    return prefix + f"{key} = {value_literal}\n" + suffix


def set_config_value(config_path: Path, dotted_key: str, raw_value: str) -> None:
    parts = dotted_key.split(".")
    if not parts or any(not part.strip() for part in parts):
        raise ValueError(f"Invalid key path '{dotted_key}'.")

    key = parts[-1].strip()
    section = ".".join(part.strip() for part in parts[:-1])
    value_literal = _to_toml_literal(raw_value)

    text = config_path.read_text(encoding="utf-8")

    if section:
        section_span = _find_section_span(text, section)
        if section_span is None:
            if text and not text.endswith("\n"):
                text += "\n"
            if text and not text.endswith("\n\n"):
                text += "\n"
            text += f"[{section}]\n{key} = {value_literal}\n"
        else:
            block_start, block_end = section_span
            section_block = text[block_start:block_end]
            updated_block = _set_key_in_block(section_block, key, value_literal)
            text = text[:block_start] + updated_block + text[block_end:]
    else:
        first_section = re.compile(r"(?m)^\[[^\]\n]+\]\s*$").search(text)
        root_end = first_section.start() if first_section else len(text)
        root_block = text[:root_end]
        updated_root = _set_key_in_block(root_block, key, value_literal)
        text = updated_root + text[root_end:]

    # Atomic write: write to a temp file in the same directory, then replace.
    # This prevents partial/corrupt config files on interruption.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        dir=str(config_path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())

        try:
            mode = config_path.stat().st_mode & 0o777
            os.chmod(tmp_path, mode)
        except OSError:
            pass

        os.replace(tmp_path, config_path)
    finally:
        tmp_path.unlink(missing_ok=True)


class ConfigWatcher:
    """Polls config file mtime and triggers reload on external changes."""

    def __init__(self, config_path: Path, on_change: Callable[[AppConfig], None], interval: float = 5.0) -> None:
        self._path = config_path
        self._on_change = on_change
        self._interval = interval
        self._last_mtime: float = self._get_mtime()
        self._last_write_time: float = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _get_mtime(self) -> float:
        try:
            return self._path.stat().st_mtime
        except OSError:
            return 0.0

    def mark_written(self) -> None:
        """Call after writing to config ourselves to avoid reload loop."""
        self._last_write_time = time.monotonic()
        self._last_mtime = self._get_mtime()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._poll, daemon=True, name="config-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _poll(self) -> None:
        while not self._stop_event.wait(self._interval):
            mtime = self._get_mtime()
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                # Skip reload if we wrote the config ourselves within 2s.
                # Prevents reload loops from our own set_config_value() calls.
                if time.monotonic() - self._last_write_time < 2.0:
                    continue
                try:
                    new_config = load_config(self._path)
                    self._on_change(new_config)
                except Exception as exc:
                    log("config-watch", f"Reload failed: {exc}")
