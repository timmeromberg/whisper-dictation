"""DictationApp — core hold-to-dictate engine."""

from __future__ import annotations

import atexit
import io
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np
from pynput import keyboard

from . import commands
from .audio_control import AudioController
from .cleaner import TextCleaner
from .compat import check_accessibility
from .compat import notify as _platform_notify
from .compat import play_wav_file as _platform_play
from .config import LANG_NAMES, AppConfig
from .history import TranscriptionHistory
from .hotkey import KEY_MAP, HotkeyListener, NSEventHotkeyListener
from .log import log
from .paster import TextPaster
from .recorder import Recorder, RecordingResult
from .rewriter import Rewriter, prompt_for_mode
from .transcriber import WhisperTranscriber, create_transcriber, create_transcriber_for

if hasattr(keyboard.Key, "cmd_r"):
    KEY_MAP.setdefault("right_command", keyboard.Key.cmd_r)
if hasattr(keyboard.Key, "shift_r"):
    KEY_MAP.setdefault("right_shift", keyboard.Key.shift_r)


class DictationApp:
    def __init__(self, config: AppConfig, listener_class: type | None = None) -> None:
        self.config = config

        self.recorder = Recorder(
            sample_rate=config.recording.sample_rate,
            device=config.recording.device,
        )
        self.transcriber = create_transcriber(config.whisper)
        self.cleaner = TextCleaner(text_commands=config.text_commands.enabled)
        self.paster = TextPaster()
        self.audio_controller = AudioController(config.audio_control)

        self._rewriter: Rewriter | None = None
        if config.rewrite.enabled and config.whisper.groq.api_key.strip():
            self._rewriter = Rewriter(
                api_key=config.whisper.groq.api_key,
                model=config.rewrite.model,
                prompt=prompt_for_mode(config.rewrite.mode, config.rewrite.prompt),
            )

        self.history = TranscriptionHistory()

        if config.custom_commands:
            commands.register_custom(config.custom_commands)

        cls = listener_class or HotkeyListener
        self._listener: HotkeyListener | NSEventHotkeyListener = cls(
            on_hold_start=self._on_hold_start,
            on_hold_end=self._on_hold_end,
            key_name=config.hotkey.key,
            on_cancel=self._on_cancel,
        )

        self._languages = list(config.whisper.languages)
        self._lang_index = 0
        # Set initial index to match active language
        if config.whisper.language in self._languages:
            self._lang_index = self._languages.index(config.whisper.language)

        self._last_tap_time = 0.0
        self._lang_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pipeline_lock = threading.Lock()
        self._threads_lock = threading.Lock()
        self._pipeline_threads: set[threading.Thread] = set()

        self._start_done = threading.Event()
        self._start_done.set()  # no pending start

        self._preview_stop = threading.Event()
        self._preview_thread: threading.Thread | None = None
        self._preview_transcriber: WhisperTranscriber | None = None

        # Optional callback for UI updates: fn(state: str, detail: str)
        # States: "idle", "recording", "transcribing", "preview", "language_changed"
        self.on_state_change: Callable[[str, str], None] | None = None

        atexit.register(self._atexit_cleanup)

    def _emit_state(self, state: str, detail: str = "") -> None:
        """Notify UI of state change. Never raises — UI failures must not break dictation."""
        if self.on_state_change:
            try:
                self.on_state_change(state, detail)
            except Exception as exc:
                log("ui", f"State callback failed ({state}): {exc}")

    @property
    def stopped(self) -> bool:
        return self._stop_event.is_set()

    @property
    def active_language(self) -> str:
        with self._lang_lock:
            return self._languages[self._lang_index]

    @property
    def languages(self) -> list[str]:
        with self._lang_lock:
            return list(self._languages)

    def set_language(self, lang: str) -> None:
        with self._lang_lock:
            if lang in self._languages:
                self._lang_index = self._languages.index(lang)
        self.transcriber.language = lang

    @property
    def listener(self) -> HotkeyListener | NSEventHotkeyListener:
        return self._listener

    def start_listener(self) -> None:
        self._listener.start()

    def _notify(self, message: str, title: str = "whisper-dic") -> None:
        """Show a platform notification banner."""
        _platform_notify(message, title)

    def _cycle_language(self) -> None:
        """Cycle to the next language and update the transcriber."""
        with self._lang_lock:
            self._lang_index = (self._lang_index + 1) % len(self._languages)
            new_lang = self._languages[self._lang_index]
        self.transcriber.language = new_lang

        display = LANG_NAMES.get(new_lang, new_lang)
        log("language", f"Switched to {display} ({new_lang})")
        self._notify(f"Language: {display}")
        self.play_beep(1200.0)
        self._emit_state("language_changed", f"{display} ({new_lang})")

    def _actionable_error(self, exc: Exception) -> str:
        """Map an exception to an actionable user-facing message."""
        err = str(exc).lower()
        provider = self.config.whisper.provider

        if any(s in err for s in ["connect", "refused", "unreachable", "resolve"]):
            if provider == "local":
                return "Whisper server unreachable. Is your whisper.cpp server running?"
            return f"Cannot reach {provider}. Check your internet connection."

        if "timeout" in err or "timed out" in err:
            return "Transcription timed out. Try a shorter recording or increase timeout in settings."

        if "401" in err or "api key" in err:
            return "API key invalid or expired. Update via menu bar \u2192 Groq API Key."

        if "429" in err or "rate limit" in err:
            return "Rate limit hit. Wait a moment, or switch to local provider."

        if "ssl" in err or "certificate" in err:
            return "SSL error. Check your internet connection or try again."

        if "413" in err or "too large" in err:
            return "Recording too large for provider. Try a shorter recording."

        if "500" in err or "502" in err or "503" in err or "server error" in err:
            return f"{provider} server error. The provider may be temporarily down."

        return f"Transcription failed: {str(exc)[:100]}"

    def _play_error_beep(self) -> None:
        """Low descending double-buzz to signal an error (non-blocking)."""
        feedback = self.config.audio_feedback
        if not feedback.enabled:
            return
        threading.Thread(
            target=self._generate_error_beep,
            args=(feedback.volume,),
            daemon=True,
            name="error-beep",
        ).start()

    def _generate_error_beep(self, volume: float) -> None:
        sample_rate = 44100
        duration = 0.15
        sample_count = int(sample_rate * duration)
        timeline = np.linspace(0, duration, sample_count, endpoint=False)
        freqs = np.linspace(400, 200, sample_count)
        tone = np.sin(2.0 * np.pi * freqs * timeline).astype(np.float32)
        tone *= volume
        gap = np.zeros(int(sample_rate * 0.08), dtype=np.float32)
        signal = np.concatenate([tone, gap, tone])
        self._play_wav(signal, sample_rate)

    def play_beep(self, frequency: float) -> None:
        """Play a short tone. Non-blocking — fires in a background thread."""
        feedback = self.config.audio_feedback
        if not feedback.enabled:
            return
        threading.Thread(
            target=self._generate_and_play_beep,
            args=(frequency, feedback.volume, feedback.duration_seconds),
            daemon=True,
            name="beep",
        ).start()

    def _generate_and_play_beep(self, frequency: float, volume: float, duration: float) -> None:
        sample_rate = 44100
        sample_count = max(1, int(sample_rate * duration))
        timeline = np.linspace(0, duration, sample_count, endpoint=False)
        tone = np.sin(2.0 * np.pi * frequency * timeline).astype(np.float32)
        tone *= volume
        self._play_wav(tone, sample_rate)

    @staticmethod
    def _play_wav(samples: np.ndarray, sample_rate: int) -> None:
        """Play audio samples via platform audio player."""
        int_samples = (samples * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(int_samples.tobytes())

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(buf.getvalue())
        tmp.close()
        try:
            _platform_play(tmp.name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _transcribe_with_retry(self, audio_bytes: bytes, max_attempts: int = 4) -> str:
        """Transcribe with retry on transient network errors (SSL, connection reset)."""
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self.transcriber.transcribe(audio_bytes)
            except Exception as exc:
                last_exc = exc
                err_str = str(exc).lower()
                is_transient = any(s in err_str for s in ["ssl", "connection", "timeout", "reset", "broken pipe"])
                if is_transient and attempt < max_attempts:
                    wait = min(0.5 * (2 ** (attempt - 1)), 8.0)
                    log("pipeline", f"Transient error ({attempt}/{max_attempts}): {exc}, retry in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("Transcription failed after retries") from last_exc

    def _try_failover(self, audio_bytes: bytes) -> str | None:
        """Attempt transcription with the other provider. Returns text or None."""
        primary = self.config.whisper.provider
        fallback = "local" if primary == "groq" else "groq"
        log("failover", f"Primary {primary} failed, trying {fallback}...")
        try:
            fb = create_transcriber_for(self.config.whisper, fallback)
            try:
                text = fb.transcribe(audio_bytes)
                log("failover", f"Fallback {fallback} succeeded")
                self._notify(f"Used {fallback} fallback ({primary} was down)")
                return text
            finally:
                fb.close()
        except Exception as fb_exc:
            log("failover", f"Fallback {fallback} also failed: {fb_exc}")
            return None

    @staticmethod
    def check_permissions() -> list[str]:
        """Check platform permissions. Returns list of missing permission names."""
        return check_accessibility()

    def startup_health_checks(self) -> bool:
        provider = self.config.whisper.provider
        if provider == "groq" and not self.config.whisper.groq.api_key.strip():
            log("startup", "Groq API key is empty. Set it via: whisper-dic set whisper.groq.api_key YOUR_KEY")
            return False
        log("startup", f"Checking Whisper provider ({provider})...")
        if not self.transcriber.health_check():
            log("startup", "Whisper provider is unreachable. Exiting.")
            return False
        log("startup", "Whisper provider is reachable.")
        return True

    def _on_hold_start(self) -> None:
        self._start_done.clear()
        try:
            if self.stopped:
                return

            try:
                started = self.recorder.start()
            except Exception as exc:
                log("recording", f"Failed to start stream: {exc}")
                self._play_error_beep()
                self._notify("Microphone unavailable. Check System Settings > Privacy > Microphone.")
                self._emit_state("idle")
                return

            if started:
                self.audio_controller.mute()
                log("recording", "Started.")
                self._emit_state("recording")
                self.play_beep(self.config.audio_feedback.start_frequency)
                self._start_preview()
        finally:
            self._start_done.set()

    def _on_cancel(self) -> None:
        """Cancel active recording — stop, discard audio, return to idle."""
        self._start_done.wait(timeout=2.0)
        if self.stopped:
            return
        log("recording", "Cancelled by Escape.")
        self._stop_preview()
        self.recorder.stop()  # discard the result
        self.audio_controller.unmute()
        self.play_beep(440.0)  # low tone = cancelled
        self._emit_state("idle")

    def _on_hold_end(self, auto_send: bool = False, command_mode: bool = False) -> None:
        # Wait for _on_hold_start to finish — prevents race on quick press/release
        self._start_done.wait(timeout=2.0)

        if self.stopped:
            return

        self._stop_preview()
        result = self.recorder.stop()

        # Unmute audio devices after recording stops
        self.audio_controller.unmute()

        if result is None:
            return

        if command_mode:
            # Triple short beep for command mode (sequential)
            dur = self.config.audio_feedback.duration_seconds
            self.play_beep(1320.0)
            time.sleep(dur + 0.02)
            self.play_beep(1320.0)
            time.sleep(dur + 0.02)
            self.play_beep(1320.0)
        elif auto_send:
            # Double beep for auto-send (sequential)
            dur = self.config.audio_feedback.duration_seconds
            self.play_beep(1100.0)
            time.sleep(dur + 0.02)
            self.play_beep(1100.0)
        else:
            self.play_beep(self.config.audio_feedback.stop_frequency)

        if result.duration_seconds < self.config.recording.min_duration:
            now = time.monotonic()
            if len(self._languages) > 1 and (now - self._last_tap_time) < 0.5:
                self._last_tap_time = 0.0
                self._cycle_language()
            else:
                self._last_tap_time = now
            self._emit_state("idle")
            return

        if result.duration_seconds > self.config.recording.max_duration:
            dur, mx = result.duration_seconds, self.config.recording.max_duration
            log("recording", f"Ignored overlong clip ({dur:.1f}s > {mx:.0f}s).")
            self._notify("Recording too long, ignored")
            self._emit_state("idle")
            return

        # Config auto-send applies to all dictations (Ctrl modifier is per-press)
        auto_send = auto_send or self.config.paste.auto_send

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
                self._emit_state("transcribing")
                try:
                    transcript = self._transcribe_with_retry(result.audio_bytes)
                except Exception:
                    if self.config.whisper.failover:
                        fallback_text = self._try_failover(result.audio_bytes)
                        if fallback_text is not None:
                            transcript = fallback_text
                        else:
                            raise
                    else:
                        raise
                log("pipeline", f"Transcript: '{transcript}'")

                cleaned = transcript
                try:
                    log("pipeline", "Cleaning transcript...")
                    cleaned = self.cleaner.clean(transcript)
                except Exception as exc:
                    log("pipeline", f"Cleanup failed, using raw transcript: {exc}")
                    cleaned = transcript

                if self._rewriter is not None and not command_mode:
                    try:
                        log("pipeline", "Rewriting with AI...")
                        cleaned = self._rewriter.rewrite(cleaned)
                    except Exception as exc:
                        log("pipeline", f"Rewrite failed, using cleaned text: {exc}")

                cleaned = cleaned.strip()
                if not cleaned:
                    log("pipeline", f"Empty after cleanup (original: '{transcript}')")
                    self._play_error_beep()
                    self._emit_state("idle")
                    return

                if command_mode:
                    log("pipeline", f"Command mode — matching: '{cleaned}'")
                    if commands.execute(cleaned):
                        self._emit_state("idle")
                    else:
                        log("command", f"No match for '{cleaned}', ignoring.")
                        self._play_error_beep()
                        self._notify(f"Unknown command: {cleaned}")
                        self._emit_state("idle")
                    return

                self.paster.paste(cleaned, auto_send=auto_send)
                self.history.add(cleaned, self.active_language, result.duration_seconds)
                log("pipeline", f"Pasted {len(cleaned)} chars (auto_send={auto_send}).")
                self._emit_state("idle")
        except Exception as exc:
            log("pipeline", f"Failed: {exc}")
            self._play_error_beep()
            self._notify(self._actionable_error(exc))
            self._emit_state("idle")
        finally:
            current = threading.current_thread()
            with self._threads_lock:
                self._pipeline_threads.discard(current)

    def _start_preview(self) -> None:
        """Start the live preview thread if streaming preview is enabled."""
        if not self.config.recording.streaming_preview:
            return
        log("preview", "Starting live preview thread...")
        self._preview_stop.clear()
        if self._preview_transcriber is None:
            try:
                pp = self.config.recording.preview_provider
                if pp:
                    self._preview_transcriber = create_transcriber_for(self.config.whisper, pp)
                else:
                    self._preview_transcriber = create_transcriber(self.config.whisper)
            except Exception as exc:
                log("preview", f"Failed to create preview transcriber: {exc}")
                return
        self._preview_thread = threading.Thread(
            target=self._run_preview_loop, daemon=True, name="preview",
        )
        self._preview_thread.start()

    def _stop_preview(self) -> None:
        """Stop the live preview thread."""
        self._preview_stop.set()
        if self._preview_thread is not None:
            self._preview_thread.join(timeout=2.0)
            self._preview_thread = None

    def _run_preview_loop(self) -> None:
        """Periodically transcribe accumulated audio and emit preview state."""
        interval = self.config.recording.preview_interval
        transcriber = self._preview_transcriber
        if transcriber is None:
            return
        # First update fires sooner for faster initial feedback
        first_wait = min(1.5, interval)
        if not self._preview_stop.wait(first_wait):
            self._do_preview(transcriber)
        while not self._preview_stop.wait(interval):
            self._do_preview(transcriber)
        self._emit_state("preview", "")

    def _do_preview(self, transcriber: WhisperTranscriber) -> None:
        """Transcribe accumulated audio and emit preview state."""
        audio = self.recorder.get_accumulated_audio()
        if audio is None:
            return
        try:
            text = transcriber.transcribe(audio)
            if text.strip():
                self._emit_state("preview", text.strip())
        except Exception as exc:
            log("preview", f"Preview transcription failed: {exc}")

    def run(self) -> int:
        missing = self.check_permissions()
        for perm in missing:
            log("startup", f"Warning: {perm} permission not granted. Check System Settings > Privacy & Security.")

        if not self.startup_health_checks():
            return 1

        self._listener.start()
        key = self.config.hotkey.key.replace("_", " ")
        lang_list = ", ".join(self.languages)
        log("ready", f"Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")
        log("ready", f"Hold {key} + Shift for voice commands.")
        log("ready", "Double-tap to cycle language.")
        log("ready", f"Languages: {lang_list} (active: {self.active_language})")

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
        if self._rewriter is not None:
            self._rewriter.close()
        if self._preview_transcriber is not None:
            self._preview_transcriber.close()
        log("shutdown", "Complete.")

    def _atexit_cleanup(self) -> None:
        """Belt-and-suspenders cleanup for abnormal exits."""
        self.history.flush()
        if self.recorder.is_recording:
            log("atexit", "Cleaning up active recording...")
            self.recorder.stop()
        if not self.stopped:
            self.transcriber.close()
