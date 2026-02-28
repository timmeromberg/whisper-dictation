"""Main entry point for system-wide hold-to-dictate on macOS."""

from __future__ import annotations

import argparse
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
import tomllib

from cleaner import TextCleaner
from hotkey import RightOptionHotkeyListener
from paster import TextPaster
from recorder import Recorder, RecordingResult
from transcriber import WhisperTranscriber


@dataclass
class HotkeyConfig:
    key: str = "right_option"


@dataclass
class RecordingConfig:
    min_duration: float = 0.3
    max_duration: float = 300.0
    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "int16"


@dataclass
class WhisperConfig:
    url: str = "http://localhost:2022/v1/audio/transcriptions"
    language: str = "en"
    model: str = "large-v3"
    timeout_seconds: float = 120.0


@dataclass
class OllamaConfig:
    enabled: bool = True
    url: str = "http://localhost:11434/api/generate"
    model: str = "qwen2.5:0.5b"
    timeout_seconds: float = 60.0
    prewarm_prompt: str = "Ready."


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
    whisper: WhisperConfig
    ollama: OllamaConfig
    audio_feedback: AudioFeedbackConfig


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name, {})
    return raw if isinstance(raw, dict) else {}


def load_config(path: Path) -> AppConfig:
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    hotkey_data = _section(data, "hotkey")
    recording_data = _section(data, "recording")
    whisper_data = _section(data, "whisper")
    ollama_data = _section(data, "ollama")
    feedback_data = _section(data, "audio_feedback")

    return AppConfig(
        hotkey=HotkeyConfig(
            key=str(hotkey_data.get("key", "right_option")),
        ),
        recording=RecordingConfig(
            min_duration=float(recording_data.get("min_duration", 0.3)),
            max_duration=float(recording_data.get("max_duration", 300.0)),
            sample_rate=int(recording_data.get("sample_rate", 16000)),
            channels=int(recording_data.get("channels", 1)),
            dtype=str(recording_data.get("dtype", "int16")),
        ),
        whisper=WhisperConfig(
            url=str(whisper_data.get("url", "http://localhost:2022/v1/audio/transcriptions")),
            language=str(whisper_data.get("language", "en")),
            model=str(whisper_data.get("model", "large-v3")),
            timeout_seconds=float(whisper_data.get("timeout_seconds", 120.0)),
        ),
        ollama=OllamaConfig(
            enabled=bool(ollama_data.get("enabled", True)),
            url=str(ollama_data.get("url", "http://localhost:11434/api/generate")),
            model=str(ollama_data.get("model", "qwen2.5:0.5b")),
            timeout_seconds=float(ollama_data.get("timeout_seconds", 60.0)),
            prewarm_prompt=str(ollama_data.get("prewarm_prompt", "Ready.")),
        ),
        audio_feedback=AudioFeedbackConfig(
            enabled=bool(feedback_data.get("enabled", True)),
            start_frequency=float(feedback_data.get("start_frequency", 880.0)),
            stop_frequency=float(feedback_data.get("stop_frequency", 660.0)),
            duration_seconds=float(feedback_data.get("duration_seconds", 0.08)),
            volume=float(feedback_data.get("volume", 0.2)),
        ),
    )


class DictationApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

        self.recorder = Recorder(
            sample_rate=config.recording.sample_rate,
            channels=config.recording.channels,
            dtype=config.recording.dtype,
        )
        self.transcriber = WhisperTranscriber(
            url=config.whisper.url,
            language=config.whisper.language,
            model=config.whisper.model,
            timeout_seconds=config.whisper.timeout_seconds,
        )
        self.cleaner = TextCleaner(
            enabled=config.ollama.enabled,
            url=config.ollama.url,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )
        self.paster = TextPaster()

        self._listener = RightOptionHotkeyListener(
            on_hold_start=self._on_hold_start,
            on_hold_end=self._on_hold_end,
            key_name=config.hotkey.key,
        )

        self._stop_event = threading.Event()
        self._pipeline_lock = threading.Lock()
        self._threads_lock = threading.Lock()
        self._pipeline_threads: set[threading.Thread] = set()

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

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
            print(f"[audio] beep failed: {exc}")

    def startup_health_checks(self) -> bool:
        print("[startup] Checking Whisper server...")
        if not self.transcriber.health_check():
            print("[startup] Whisper is unreachable at configured URL. Exiting.")
            return False
        print("[startup] Whisper is reachable.")

        if not self.cleaner.enabled:
            print("[startup] Ollama cleanup disabled by config.")
            return True

        print("[startup] Checking Ollama server...")
        if not self.cleaner.health_check():
            print("[startup] Warning: Ollama unreachable. Continuing without cleanup.")
            self.cleaner.enabled = False
            return True

        print("[startup] Ollama is reachable. Pre-warming model...")
        if not self.cleaner.prewarm(prompt=self.config.ollama.prewarm_prompt):
            print("[startup] Warning: Ollama pre-warm failed. Continuing without cleanup.")
            self.cleaner.enabled = False
            return True

        print("[startup] Ollama model pre-warmed.")
        return True

    def _on_hold_start(self) -> None:
        if self.stopped:
            return

        try:
            started = self.recorder.start()
        except Exception as exc:
            print(f"[recording] Failed to start stream: {exc}")
            return

        if started:
            self._play_beep(self.config.audio_feedback.start_frequency)
            print("[recording] Started.")

    def _on_hold_end(self) -> None:
        if self.stopped:
            return

        result = self.recorder.stop()
        if result is None:
            return

        self._play_beep(self.config.audio_feedback.stop_frequency)

        if result.duration_seconds < self.config.recording.min_duration:
            print(
                f"[recording] Ignored short tap ({result.duration_seconds:.2f}s < "
                f"{self.config.recording.min_duration:.2f}s)."
            )
            return

        if result.duration_seconds > self.config.recording.max_duration:
            print(
                f"[recording] Ignored overlong clip ({result.duration_seconds:.2f}s > "
                f"{self.config.recording.max_duration:.2f}s)."
            )
            return

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(result,),
            daemon=True,
            name="dictation-pipeline",
        )

        with self._threads_lock:
            self._pipeline_threads.add(worker)

        worker.start()

    def _run_pipeline(self, result: RecordingResult) -> None:
        try:
            with self._pipeline_lock:
                print("[pipeline] Transcribing...")
                transcript = self.transcriber.transcribe(result.wav_bytes)

                cleaned = transcript
                if self.cleaner.enabled:
                    try:
                        print("[pipeline] Cleaning transcript...")
                        cleaned = self.cleaner.clean(transcript)
                    except Exception as exc:
                        print(f"[pipeline] Cleanup failed, using raw transcript: {exc}")
                        cleaned = transcript

                cleaned = cleaned.strip()
                if not cleaned:
                    print("[pipeline] Nothing to paste after cleanup.")
                    return

                self.paster.paste(cleaned)
                print(f"[pipeline] Pasted {len(cleaned)} chars.")
        except Exception as exc:
            print(f"[pipeline] Failed: {exc}")
        finally:
            current = threading.current_thread()
            with self._threads_lock:
                self._pipeline_threads.discard(current)

    def run(self) -> int:
        if not self.startup_health_checks():
            return 1

        self._listener.start()
        print("[ready] Hold right Option to dictate. Release to transcribe and paste.")

        while not self.stopped:
            time.sleep(0.1)

        return 0

    def stop(self) -> None:
        if self.stopped:
            return

        self._stop_event.set()
        print("[shutdown] Stopping listener and recorder...")

        self._listener.stop()
        self.recorder.stop()

        with self._threads_lock:
            threads = list(self._pipeline_threads)

        for thread in threads:
            thread.join(timeout=2.0)

        self.transcriber.close()
        self.cleaner.close()
        print("[shutdown] Complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="System-wide hold-to-dictate tool")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("config.toml")),
        help="Path to config.toml",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return 1

    try:
        config = load_config(config_path)
    except Exception as exc:
        print(f"Failed to load config: {exc}")
        return 1

    app = DictationApp(config)

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


if __name__ == "__main__":
    raise SystemExit(main())
