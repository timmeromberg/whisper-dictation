"""Main entry point for system-wide hold-to-dictate on macOS."""

from __future__ import annotations

import argparse
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import tomllib
from pynput import keyboard

import commands
from audio_control import AudioControlConfig, AudioController
from cleaner import TextCleaner
from hotkey import KEY_MAP, RightOptionHotkeyListener
from log import log
from paster import TextPaster
from recorder import Recorder, RecordingResult
from transcriber import GroqWhisperTranscriber, LocalWhisperTranscriber, create_transcriber

if hasattr(keyboard.Key, "cmd_r"):
    KEY_MAP.setdefault("right_command", keyboard.Key.cmd_r)
if hasattr(keyboard.Key, "shift_r"):
    KEY_MAP.setdefault("right_shift", keyboard.Key.shift_r)


@dataclass
class HotkeyConfig:
    key: str = "right_option"


@dataclass
class RecordingConfig:
    min_duration: float = 0.3
    max_duration: float = 300.0
    sample_rate: int = 16000


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
class AppConfig:
    hotkey: HotkeyConfig
    recording: RecordingConfig
    paste: PasteConfig
    text_commands: TextCommandsConfig
    whisper: WhisperConfig
    audio_feedback: AudioFeedbackConfig
    audio_control: AudioControlConfig = field(default_factory=AudioControlConfig)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    cursor: Any = data
    for part in name.split("."):
        if not isinstance(cursor, dict):
            return {}
        cursor = cursor.get(part, {})
    return cursor if isinstance(cursor, dict) else {}


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

    return AppConfig(
        hotkey=HotkeyConfig(
            key=str(hotkey_data.get("key", "right_option")),
        ),
        recording=RecordingConfig(
            min_duration=float(recording_data.get("min_duration", 0.3)),
            max_duration=float(recording_data.get("max_duration", 300.0)),
            sample_rate=int(recording_data.get("sample_rate", 16000)),
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
    )


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

    config_path.write_text(text, encoding="utf-8")


class DictationApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

        self.recorder = Recorder(
            sample_rate=config.recording.sample_rate,
        )
        self.transcriber = create_transcriber(config.whisper)
        self.cleaner = TextCleaner(text_commands=config.text_commands.enabled)
        self.paster = TextPaster()
        self.audio_controller = AudioController(config.audio_control)

        self._listener = RightOptionHotkeyListener(
            on_hold_start=self._on_hold_start,
            on_hold_end=self._on_hold_end,
            key_name=config.hotkey.key,
        )

        self._languages = list(config.whisper.languages)
        self._lang_index = 0
        # Set initial index to match active language
        if config.whisper.language in self._languages:
            self._lang_index = self._languages.index(config.whisper.language)

        self._last_tap_time = 0.0
        self._stop_event = threading.Event()
        self._pipeline_lock = threading.Lock()
        self._threads_lock = threading.Lock()
        self._pipeline_threads: set[threading.Thread] = set()

        # Optional callback for UI updates: fn(state: str, detail: str)
        # States: "idle", "recording", "transcribing", "language_changed"
        self.on_state_change: Callable[[str, str], None] | None = None

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    def _notify(self, message: str, title: str = "whisper-dic") -> None:
        """Show a macOS notification banner."""
        # Escape backslashes and quotes to prevent AppleScript injection
        safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        try:
            subprocess.Popen(
                ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _cycle_language(self) -> None:
        """Cycle to the next language and update the transcriber."""
        self._lang_index = (self._lang_index + 1) % len(self._languages)
        new_lang = self._languages[self._lang_index]
        self.transcriber.language = new_lang

        LANG_NAMES = {
            "en": "English", "nl": "Dutch", "de": "German", "fr": "French",
            "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
            "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "auto": "Auto-detect",
            "ar": "Arabic", "hi": "Hindi", "pl": "Polish", "sv": "Swedish",
            "tr": "Turkish", "uk": "Ukrainian", "da": "Danish", "no": "Norwegian",
        }
        display = LANG_NAMES.get(new_lang, new_lang)
        log("language", f"Switched to {display} ({new_lang})")
        self._notify(f"Language: {display}")
        self._play_beep(1200.0)
        if self.on_state_change:
            self.on_state_change("language_changed", f"{display} ({new_lang})")

    def _play_error_beep(self) -> None:
        """Low descending double-buzz to signal an error."""
        feedback = self.config.audio_feedback
        if not feedback.enabled:
            return

        sample_rate = 44100
        duration = 0.15
        sample_count = int(sample_rate * duration)
        timeline = np.linspace(0, duration, sample_count, endpoint=False)
        # Descending buzz: 400Hz -> 200Hz
        freqs = np.linspace(400, 200, sample_count)
        tone = np.sin(2.0 * np.pi * freqs * timeline).astype(np.float32)
        tone *= feedback.volume
        # Two buzzes with a gap
        gap = np.zeros(int(sample_rate * 0.08), dtype=np.float32)
        signal = np.concatenate([tone, gap, tone])

        try:
            sd.play(signal, samplerate=sample_rate, blocking=False)
        except Exception:
            pass

    def _play_beep(self, frequency: float) -> None:
        feedback = self.config.audio_feedback
        if not feedback.enabled:
            return

        sample_rate = 44100
        sample_count = max(1, int(sample_rate * feedback.duration_seconds))
        timeline = np.linspace(0, feedback.duration_seconds, sample_count, endpoint=False)
        tone = np.sin(2.0 * np.pi * frequency * timeline).astype(np.float32)
        tone *= feedback.volume

        try:
            sd.play(tone, samplerate=sample_rate, blocking=False)
        except Exception as exc:
            log("audio", f"Beep failed: {exc}")

    def _transcribe_with_retry(self, audio_bytes: bytes, max_attempts: int = 3) -> str:
        """Transcribe with retry on transient network errors (SSL, connection reset)."""
        for attempt in range(1, max_attempts + 1):
            try:
                return self.transcriber.transcribe(audio_bytes)
            except Exception as exc:
                err_str = str(exc).lower()
                is_transient = any(s in err_str for s in ["ssl", "connection", "timeout", "reset", "broken pipe"])
                if is_transient and attempt < max_attempts:
                    wait = attempt * 0.5
                    log("pipeline", f"Transient error (attempt {attempt}/{max_attempts}): {exc}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def startup_health_checks(self) -> bool:
        provider = self.config.whisper.provider
        log("startup", f"Checking Whisper provider ({provider})...")
        if not self.transcriber.health_check():
            log("startup", "Whisper provider is unreachable. Exiting.")
            return False
        log("startup", "Whisper provider is reachable.")
        log("startup", "Regex-based filler removal enabled.")
        return True

    def _on_hold_start(self) -> None:
        if self.stopped:
            return

        # Mute audio devices before recording starts
        self.audio_controller.mute()

        try:
            started = self.recorder.start()
        except Exception as exc:
            log("recording", f"Failed to start stream: {exc}")
            self.audio_controller.unmute()
            return

        if started:
            self._play_beep(self.config.audio_feedback.start_frequency)
            log("recording", "Started.")
            if self.on_state_change:
                self.on_state_change("recording", "")

    def _on_hold_end(self, auto_send: bool = False, command_mode: bool = False) -> None:
        if self.stopped:
            return

        result = self.recorder.stop()

        # Unmute audio devices after recording stops
        self.audio_controller.unmute()

        if result is None:
            return

        if command_mode:
            # Triple short beep for command mode
            self._play_beep(1320.0)
            time.sleep(0.08)
            self._play_beep(1320.0)
            time.sleep(0.08)
            self._play_beep(1320.0)
        elif auto_send:
            # Double beep for auto-send
            self._play_beep(1100.0)
            time.sleep(0.1)
            self._play_beep(1100.0)
        else:
            self._play_beep(self.config.audio_feedback.stop_frequency)

        if result.duration_seconds < self.config.recording.min_duration:
            now = time.monotonic()
            if len(self._languages) > 1:
                elapsed = now - self._last_tap_time
                self._last_tap_time = now
                if elapsed < 1.0:
                    # Double-tap detected — cycle language
                    self._last_tap_time = 0.0  # reset so triple-tap doesn't cycle again
                    self._cycle_language()
            return

        if result.duration_seconds > self.config.recording.max_duration:
            log("recording", f"Ignored overlong clip ({result.duration_seconds:.2f}s > {self.config.recording.max_duration:.2f}s).")
            return

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(result, auto_send, command_mode),
            daemon=True,
            name="dictation-pipeline",
        )

        with self._threads_lock:
            self._pipeline_threads.add(worker)

        worker.start()

    def _run_pipeline(self, result: RecordingResult, auto_send: bool = False, command_mode: bool = False) -> None:
        try:
            with self._pipeline_lock:
                size_kb = len(result.audio_bytes) / 1024
                log("pipeline", f"Transcribing {result.duration_seconds:.1f}s ({size_kb:.0f} KB)...")
                if self.on_state_change:
                    self.on_state_change("transcribing", "")
                transcript = self._transcribe_with_retry(result.audio_bytes)
                log("pipeline", f"Transcript: '{transcript}'")

                cleaned = transcript
                if self.cleaner.enabled:
                    try:
                        log("pipeline", "Cleaning transcript...")
                        cleaned = self.cleaner.clean(transcript)
                    except Exception as exc:
                        log("pipeline", f"Cleanup failed, using raw transcript: {exc}")
                        cleaned = transcript

                cleaned = cleaned.strip()
                if not cleaned:
                    log("pipeline", f"Empty after cleanup (original: '{transcript}')")
                    return

                if command_mode:
                    log("pipeline", f"Command mode — matching: '{cleaned}'")
                    if commands.execute(cleaned):
                        if self.on_state_change:
                            self.on_state_change("idle", "")
                    else:
                        log("command", f"No match for '{cleaned}', ignoring.")
                        if self.on_state_change:
                            self.on_state_change("idle", "")
                    return

                self.paster.paste(cleaned, auto_send=auto_send)
                log("pipeline", f"Pasted {len(cleaned)} chars (auto_send={auto_send}).")
                if self.on_state_change:
                    self.on_state_change("idle", "")
        except Exception as exc:
            log("pipeline", f"Failed: {exc}")
            # Audio + visual feedback so the user knows something went wrong
            self._play_error_beep()
            self._notify(f"Transcription failed: {exc}")
            if self.on_state_change:
                self.on_state_change("idle", "")
        finally:
            current = threading.current_thread()
            with self._threads_lock:
                self._pipeline_threads.discard(current)

    def run(self) -> int:
        if not self.startup_health_checks():
            return 1

        self._listener.start()
        key = self.config.hotkey.key.replace("_", " ")
        lang_list = ", ".join(self._languages)
        log("ready", f"Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")
        log("ready", f"Hold {key} + Shift for voice commands.")
        log("ready", f"Quick tap to cycle language.")
        log("ready", f"Languages: {lang_list} (active: {self._languages[self._lang_index]})")

        while not self.stopped:
            time.sleep(0.1)

        return 0

    def stop(self) -> None:
        if self.stopped:
            return

        self._stop_event.set()
        log("shutdown", "Stopping listener and recorder...")

        self._listener.stop()
        self.recorder.stop()

        with self._threads_lock:
            threads = list(self._pipeline_threads)

        for thread in threads:
            thread.join(timeout=2.0)
            if thread.is_alive():
                log("shutdown", f"Warning: {thread.name} did not finish in time")

        self.transcriber.close()
        self.cleaner.close()
        log("shutdown", "Complete.")


def _load_config_from_path(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return load_config(config_path)


def _print_status(config_path: Path, config: AppConfig) -> None:
    print(f"[status] Config: {config_path}")
    print(f"[status] hotkey.key = {config.hotkey.key}")
    print(
        "[status] recording = "
        f"min_duration={config.recording.min_duration}, "
        f"max_duration={config.recording.max_duration}, "
        f"sample_rate={config.recording.sample_rate}"
    )
    print(
        "[status] whisper = "
        f"provider={config.whisper.provider}, "
        f"language={config.whisper.language}, "
        f"timeout_seconds={config.whisper.timeout_seconds}"
    )
    print(
        "[status] whisper.local = "
        f"url={config.whisper.local.url}, model={config.whisper.local.model}"
    )
    print(
        "[status] whisper.groq = "
        f"url={config.whisper.groq.url}, model={config.whisper.groq.model}, "
        f"api_key={'set' if config.whisper.groq.api_key.strip() else 'missing'}"
    )


def _check_endpoint_reachability(config: AppConfig) -> tuple[bool, bool, bool]:
    local = LocalWhisperTranscriber(
        url=config.whisper.local.url,
        language=config.whisper.language,
        model=config.whisper.local.model,
        timeout_seconds=config.whisper.timeout_seconds,
    )
    groq = GroqWhisperTranscriber(
        api_key=config.whisper.groq.api_key,
        url=config.whisper.groq.url,
        language=config.whisper.language,
        model=config.whisper.groq.model,
        timeout_seconds=config.whisper.timeout_seconds,
    )
    current = create_transcriber(config.whisper)

    try:
        local_ok = local.health_check()
        groq_ok = groq.health_check()
        current_ok = current.health_check()
    finally:
        local.close()
        groq.close()
        current.close()

    return local_ok, groq_ok, current_ok


def command_status(config_path: Path) -> int:
    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    _print_status(config_path, config)

    local_ok, groq_ok, current_ok = _check_endpoint_reachability(config)

    print(f"[status] local endpoint reachable: {'yes' if local_ok else 'no'}")
    print(f"[status] groq endpoint reachable: {'yes' if groq_ok else 'no'}")
    print(
        f"[status] active provider ({config.whisper.provider}) reachable: "
        f"{'yes' if current_ok else 'no'}"
    )

    return 0


def command_provider(config_path: Path, provider: str | None) -> int:
    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    if provider is None:
        print(config.whisper.provider)
        return 0

    if provider == "groq" and not config.whisper.groq.api_key.strip():
        try:
            entered_key = input("Groq API key missing. Enter API key (leave blank to cancel): ").strip()
        except EOFError:
            entered_key = ""

        if not entered_key:
            print("[config] Provider unchanged because no API key was provided.")
            return 1

        set_config_value(config_path, "whisper.groq.api_key", entered_key)
        print("[config] Stored whisper.groq.api_key.")

    set_config_value(config_path, "whisper.provider", provider)
    print(f"[config] whisper.provider set to '{provider}'.")
    return 0


def command_set(config_path: Path, key: str, value: str) -> int:
    try:
        _load_config_from_path(config_path)
        set_config_value(config_path, key, value)
    except Exception as exc:
        print(f"Failed to set '{key}': {exc}")
        return 1

    print(f"[config] Set {key} = {_to_toml_literal(value)}")
    return 0


def command_run(config_path: Path) -> int:
    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    try:
        app = DictationApp(config)
    except Exception as exc:
        print(f"Failed to initialize app: {exc}")
        return 1

    def _handle_signal(signum: int, _frame) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        print(f"\n[signal] Received {name}.")
        app.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        return app.run()
    except KeyboardInterrupt:
        app.stop()
        return 0
    finally:
        app.stop()


def command_setup(config_path: Path) -> int:
    try:
        _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    try:
        from menu import run_setup_menu
    except Exception as exc:
        print(f"Failed to load setup menu: {exc}")
        return 1

    try:
        action = run_setup_menu(config_path)
    except KeyboardInterrupt:
        print()
        return 0
    except Exception as exc:
        print(f"Setup failed: {exc}")
        return 1

    if action == "start":
        return command_run(config_path)
    return 0


_PLIST_LABEL = "com.whisper.dictation"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_LOG_PATH = "/tmp/whisper-dictation.log"


def _generate_plist() -> str:
    script_path = Path(__file__).resolve().parent / "whisper-dic"
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{script_path}</string>
    <string>menubar</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{script_path.parent}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>{_LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>{_LOG_PATH}</string>
</dict>
</plist>
"""


def command_install() -> int:
    if _PLIST_PATH.exists():
        print(f"[install] Already installed at {_PLIST_PATH}")
        print("[install] Run 'whisper-dic uninstall' first to reinstall.")
        return 1

    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(_generate_plist(), encoding="utf-8")
    print(f"[install] Created {_PLIST_PATH}")

    result = subprocess.run(["launchctl", "load", str(_PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[install] launchctl load failed: {result.stderr.strip()}")
        return 1

    print("[install] Loaded into launchd. whisper-dic will start at login.")
    print(f"[install] Logs: {_LOG_PATH}")
    return 0


def command_uninstall() -> int:
    if not _PLIST_PATH.exists():
        print("[uninstall] Not installed.")
        return 1

    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True, text=True)
    _PLIST_PATH.unlink()
    print(f"[uninstall] Removed {_PLIST_PATH}")
    print("[uninstall] whisper-dic will no longer start at login.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.toml")),
        help="Path to config.toml",
    )

    parser = argparse.ArgumentParser(
        description="System-wide hold-to-dictate tool",
        parents=[config_parent],
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "run",
        parents=[config_parent],
        help="Start dictation",
    )
    subparsers.add_parser(
        "setup",
        parents=[config_parent],
        help="Open interactive setup menu",
    )

    subparsers.add_parser(
        "status",
        parents=[config_parent],
        help="Show current config and endpoint reachability",
    )

    provider_parser = subparsers.add_parser(
        "provider",
        parents=[config_parent],
        help="Show or set the whisper provider",
    )
    provider_parser.add_argument(
        "provider",
        nargs="?",
        choices=["local", "groq"],
        help="Provider to set",
    )

    set_parser = subparsers.add_parser(
        "set",
        parents=[config_parent],
        help="Set a config key (for example whisper.groq.api_key sk-xxx)",
    )
    set_parser.add_argument("key", help="Dotted key path, for example whisper.language")
    set_parser.add_argument("value", help="Value to set")

    subparsers.add_parser(
        "menubar",
        parents=[config_parent],
        help="Run with menu bar icon",
    )
    subparsers.add_parser(
        "discover",
        parents=[config_parent],
        help="Discover audio devices on the local network",
    )
    subparsers.add_parser(
        "install",
        help="Install as login item (start at login, auto-restart)",
    )
    subparsers.add_parser(
        "uninstall",
        help="Remove login item",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    command = args.command or "run"

    if command == "run":
        return command_run(config_path)
    if command == "menubar":
        from menubar import run_menubar
        return run_menubar(config_path)
    if command == "setup":
        return command_setup(config_path)
    if command == "status":
        return command_status(config_path)
    if command == "provider":
        return command_provider(config_path, args.provider)
    if command == "set":
        return command_set(config_path, args.key, args.value)
    if command == "discover":
        from audio_control import discover
        discover(config_path)
        return 0
    if command == "install":
        return command_install()
    if command == "uninstall":
        return command_uninstall()

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
