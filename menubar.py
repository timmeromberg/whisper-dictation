"""macOS menu bar integration for whisper-dic."""

from __future__ import annotations

import signal
import threading
from pathlib import Path
from typing import Any

import rumps
import sounddevice as sd

from cli import _PLIST_PATH, command_install, command_uninstall
from config import LANG_NAMES, ConfigWatcher, load_config, set_config_value
from dictation import DictationApp
from overlay import RecordingOverlay
from transcriber import create_transcriber

PROVIDER_OPTIONS = ["local", "groq"]
LANGUAGE_OPTIONS = ["en", "auto", "nl", "de", "fr", "es", "ja", "zh", "ko", "pt", "it", "ru"]
HOTKEY_OPTIONS = ["left_option", "right_option", "left_command", "right_command", "left_shift", "right_shift"]


class DictationMenuBar(rumps.App):
    def __init__(self, config_path: Path) -> None:
        super().__init__("", quit_button=None)
        self.icon = None
        self.title = "\U0001f3a4"  # microphone emoji

        self.config_path = config_path
        self.config = load_config(config_path)

        self._app = DictationApp(self.config)
        self._app.on_state_change = self._on_state_change
        self._is_recording = False
        self._level_timer = rumps.Timer(self._update_level, 0.15)
        self._health_timer = rumps.Timer(self._periodic_health_check, 60)
        self._provider_healthy = True
        self._health_notified = False
        self._config_watcher = ConfigWatcher(config_path, self._on_config_changed)
        self._overlay = RecordingOverlay()
        self._volume_last_change = 0.0

        self._status_item = rumps.MenuItem("Status: Idle")
        self._status_item.set_callback(None)

        self._lang_menu = self._build_language_menu()
        self._provider_menu = self._build_provider_menu()
        self._hotkey_menu = self._build_hotkey_menu()
        self._volume_menu, self._volume_slider = self._build_volume_menu()
        self._mic_menu = self._build_microphone_menu()
        self._textcmds_item, self._autosend_item, self._audioctrl_item, self._failover_item = (
            self._build_toggle_items()
        )
        self._help_menu = self._build_help_menu()
        self._history_menu = rumps.MenuItem("History")
        self._rebuild_history_menu()

        self.menu = [
            self._status_item,
            None,
            self._lang_menu,
            self._provider_menu,
            self._hotkey_menu,
            self._volume_menu,
            self._mic_menu,
            self._textcmds_item,
            self._autosend_item,
            self._audioctrl_item,
            self._failover_item,
            None,
            self._history_menu,
            self._build_recording_menu(),
            rumps.MenuItem("Groq API Key...", callback=self._set_groq_key),
            None,
            rumps.MenuItem("Check Status", callback=self._check_status),
            rumps.MenuItem("View Logs", callback=self._view_logs),
            self._build_service_menu(),
            None,
            self._help_menu,
            self._version_item(),
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _build_language_menu(self) -> rumps.MenuItem:
        active_lang = self._app.active_language
        display = LANG_NAMES.get(active_lang, active_lang)
        menu = rumps.MenuItem(f"Language: {display}")
        for lang in self._app.languages:
            name = LANG_NAMES.get(lang, lang)
            item = rumps.MenuItem(f"{name} ({lang})", callback=self._switch_language)
            if lang == active_lang:
                item.state = 1
            menu.add(item)
        return menu

    def _build_provider_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem(f"Provider: {self.config.whisper.provider}")
        for p in PROVIDER_OPTIONS:
            item = rumps.MenuItem(p, callback=self._switch_provider)
            if p == self.config.whisper.provider:
                item.state = 1
            menu.add(item)
        return menu

    def _build_hotkey_menu(self) -> rumps.MenuItem:
        current_key = self.config.hotkey.key
        menu = rumps.MenuItem(f"Hotkey: {current_key.replace('_', ' ')}")
        for hk in HOTKEY_OPTIONS:
            item = rumps.MenuItem(hk.replace("_", " "), callback=self._switch_hotkey)
            item._hotkey_value = hk
            if hk == current_key:
                item.state = 1
            menu.add(item)
        return menu

    def _build_volume_menu(self) -> tuple[rumps.MenuItem, rumps.SliderMenuItem]:
        vol_pct = int(self.config.audio_feedback.volume * 100)
        menu = rumps.MenuItem(f"Volume: {vol_pct}%")
        slider = rumps.SliderMenuItem(
            value=vol_pct, min_value=0, max_value=100,
            callback=self._on_volume_slide,
        )
        menu.add(slider)
        return menu, slider

    def _build_microphone_menu(self) -> rumps.MenuItem:
        current = self.config.recording.device
        label = current or "System Default"
        menu = rumps.MenuItem(f"Microphone: {label}")
        # "System Default" option
        default_item = rumps.MenuItem("System Default", callback=self._switch_microphone)
        default_item._mic_device = None  # type: ignore[attr-defined]
        if current is None:
            default_item.state = 1
        menu.add(default_item)
        # List all input devices
        try:
            for dev in sd.query_devices():
                if dev["max_input_channels"] > 0:  # type: ignore[index]
                    name = str(dev["name"])  # type: ignore[index]
                    item = rumps.MenuItem(name, callback=self._switch_microphone)
                    item._mic_device = name  # type: ignore[attr-defined]
                    if name == current:
                        item.state = 1
                    menu.add(item)
        except Exception:
            pass
        return menu

    def _build_toggle_items(self) -> tuple[rumps.MenuItem, rumps.MenuItem, rumps.MenuItem, rumps.MenuItem]:
        tc_on = self.config.text_commands.enabled
        textcmds = rumps.MenuItem(f"Text Commands: {'on' if tc_on else 'off'}", callback=self._toggle_text_commands)

        as_on = self.config.paste.auto_send
        autosend = rumps.MenuItem(f"Auto-Send: {'on' if as_on else 'off'}", callback=self._toggle_auto_send)

        ac_on = self.config.audio_control.enabled
        audioctrl = rumps.MenuItem(f"Audio Control: {'on' if ac_on else 'off'}", callback=self._toggle_audio_control)

        fo_on = self.config.whisper.failover
        failover = rumps.MenuItem(f"Failover: {'on' if fo_on else 'off'}", callback=self._toggle_failover)

        return textcmds, autosend, audioctrl, failover

    def _build_help_menu(self) -> rumps.MenuItem:
        key_display = self.config.hotkey.key.replace("_", " ")
        menu = rumps.MenuItem("How to Use")
        for label in [
            f"Hold {key_display} — dictate",
            f"Hold {key_display} + Ctrl — dictate + send",
            f"Hold {key_display} + Shift — voice command",
            f"Double-tap {key_display} — cycle language",
        ]:
            item = rumps.MenuItem(label)
            item.set_callback(None)
            menu.add(item)

        voice_cmds = rumps.MenuItem("Voice Commands")
        for label in [
            "copy / cut / paste / select all",
            "undo / redo / save / find",
            "delete / enter / tab / escape",
            "screenshot / bold / new tab",
        ]:
            item = rumps.MenuItem(label)
            item.set_callback(None)
            voice_cmds.add(item)
        menu.add(voice_cmds)

        text_cmds = rumps.MenuItem("Text Commands (say these)")
        for label in [
            "period / comma / question mark",
            "new line / new paragraph",
            "open quote / close quote",
            "colon / semicolon / dash",
        ]:
            item = rumps.MenuItem(label)
            item.set_callback(None)
            text_cmds.add(item)
        menu.add(text_cmds)

        return menu

    # --- History ---

    def _rebuild_history_menu(self) -> None:
        # rumps MenuItem._menu is None before the run loop starts,
        # so we can only clear() after first render.
        try:
            self._history_menu.clear()
        except AttributeError:
            pass  # first call during __init__ — menu not yet attached

        entries = self._app.history.entries()
        if not entries:
            item = rumps.MenuItem("No entries yet")
            item.set_callback(None)
            self._history_menu.add(item)
            return

        import time as _time
        now = _time.time()
        for entry in entries[:20]:
            age = now - entry.timestamp
            if age < 60:
                ago = f"{int(age)}s ago"
            elif age < 3600:
                ago = f"{int(age / 60)}m ago"
            else:
                ago = f"{int(age / 3600)}h ago"
            display = entry.text[:50] + ("..." if len(entry.text) > 50 else "")
            item = rumps.MenuItem(f"{display}  ({ago})", callback=self._copy_history_entry)
            item._history_text = entry.text
            self._history_menu.add(item)

        self._history_menu.add(None)
        self._history_menu.add(rumps.MenuItem("Clear History", callback=self._clear_history))

    def _copy_history_entry(self, sender: Any) -> None:
        import subprocess
        subprocess.run(["pbcopy"], input=sender._history_text.encode(), check=True)
        rumps.notification("whisper-dic", "Copied", sender._history_text[:80])

    def _clear_history(self, _sender: Any) -> None:
        self._app.history.clear()
        self._rebuild_history_menu()

    # --- Config helpers ---

    def _set_config(self, key: str, value: str) -> None:
        """Write a config value and mark the write to avoid reload loop."""
        set_config_value(self.config_path, key, value)
        self._config_watcher.mark_written()

    # --- State callbacks ---

    _LEVEL_BARS = ["\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586", "\u2587", "\u2588"]

    def _on_state_change(self, state: str, detail: str) -> None:
        if state == "recording":
            self._is_recording = True
            self.title = "\U0001f534"
            self._status_item.title = "Status: Recording..."
            self._level_timer.start()
            self._overlay.show_recording()
        elif state == "transcribing":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\u23f3"
            self._status_item.title = "Status: Transcribing..."
            self._overlay.show_transcribing()
        elif state == "idle":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._overlay.hide()
            self._rebuild_history_menu()
        elif state == "language_changed":
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._lang_menu.title = f"Language: {detail}"
            # Update checkmarks
            new_lang = self._app.active_language
            for item in self._lang_menu.values():
                item.state = 1 if f"({new_lang})" in item.title else 0

    def _periodic_health_check(self, _timer: Any) -> None:
        def _run():
            ok = self._app.transcriber.health_check()
            if not ok and self._provider_healthy:
                # Provider just went down
                self._provider_healthy = False
                self._status_item.title = "Status: Provider Unreachable"
                self.title = "\u26a0\ufe0f"  # warning emoji
                if not self._health_notified:
                    provider = self.config.whisper.provider
                    rumps.notification("whisper-dic", "Provider Unreachable",
                                       f"{provider} is not responding. Dictation may fail.")
                    self._health_notified = True
            elif ok and not self._provider_healthy:
                # Provider recovered
                self._provider_healthy = True
                self._health_notified = False
                if not self._is_recording:
                    self._status_item.title = "Status: Idle"
                    self.title = "\U0001f3a4"
                rumps.notification("whisper-dic", "Provider Online",
                                   "Connection restored. Dictation is ready.")
        threading.Thread(target=_run, daemon=True).start()

    def _update_level(self, _timer: Any) -> None:
        if not self._is_recording:
            return
        peak = self._app.recorder.read_peak()
        # Use log scale: normal speech (~500-5000) should fill most of the meter
        import math
        if peak > 0:
            db = 20.0 * math.log10(peak / 32768.0)  # dBFS, 0 = max, negative = quieter
            # Map -60 dBFS..0 dBFS to 0.0..1.0 (speech is typically -30 to -10 dBFS)
            normalized = max(0.0, min(1.0, (db + 60.0) / 60.0))
        else:
            normalized = 0.0
        bar_index = min(int(normalized * len(self._LEVEL_BARS)), len(self._LEVEL_BARS) - 1)
        self.title = f"\U0001f534{self._LEVEL_BARS[bar_index]}"

    # --- Setting actions ---

    def _switch_language(self, sender: Any) -> None:
        # Extract lang code from "English (en)"
        lang = sender.title.split("(")[-1].rstrip(")")
        if lang == self._app.active_language:
            return
        self._app.set_language(lang)
        display = LANG_NAMES.get(lang, lang)
        self._lang_menu.title = f"Language: {display}"
        for item in self._lang_menu.values():
            item.state = 1 if sender.title == item.title else 0
        self._set_config("whisper.language", lang)
        print(f"[menubar] Language: {display} ({lang})")

    def _switch_provider(self, sender: Any) -> None:
        provider = sender.title
        if provider == self.config.whisper.provider:
            return
        if provider == "groq" and not self.config.whisper.groq.api_key.strip():
            if not self._prompt_groq_key():
                return
        self._set_config("whisper.provider", provider)
        self.config = load_config(self.config_path)
        # Recreate transcriber with new provider
        self._app.transcriber.close()
        self._app.transcriber = create_transcriber(self.config.whisper)
        self._provider_menu.title = f"Provider: {provider}"
        for item in self._provider_menu.values():
            item.state = 1 if item.title == provider else 0
        print(f"[menubar] Provider: {provider}")
        # Verify connection in background
        threading.Thread(target=self._check_provider_health, daemon=True).start()

    def _prompt_groq_key(self) -> bool:
        """Prompt for Groq API key via dialog. Returns True if key was set."""
        response = rumps.Window(
            title="Groq API Key",
            message="Enter your API key from console.groq.com:",
            default_text="",
            ok="Save",
            cancel="Cancel",
            secure=True,
        ).run()
        if not response.clicked or not response.text.strip():
            return False
        self._set_config("whisper.groq.api_key", response.text.strip())
        self.config = load_config(self.config_path)
        return True

    def _set_groq_key(self, _sender: Any) -> None:
        """Menu item callback to set/update Groq API key."""
        if self._prompt_groq_key():
            # If currently using groq, recreate transcriber with new key
            if self.config.whisper.provider == "groq":
                self._app.transcriber.close()
                self._app.transcriber = create_transcriber(self.config.whisper)
                threading.Thread(target=self._check_provider_health, daemon=True).start()
            rumps.notification("whisper-dic", "API Key Updated", "Groq API key saved.")

    def _check_provider_health(self) -> None:
        """Run a health check and notify the user of the result."""
        ok = self._app.transcriber.health_check()
        provider = self.config.whisper.provider
        if ok:
            rumps.notification("whisper-dic", "Connection Verified",
                               f"{provider} provider is reachable.")
        else:
            rumps.notification("whisper-dic", "Connection Failed",
                               f"{provider} provider is unreachable. Check your settings.")

    def _switch_hotkey(self, sender: Any) -> None:
        hk = sender._hotkey_value
        if hk == self.config.hotkey.key:
            return
        self._set_config("hotkey.key", hk)
        self.config.hotkey.key = hk
        self._app.listener.set_key(hk)
        self._hotkey_menu.title = f"Hotkey: {hk.replace('_', ' ')}"
        for item in self._hotkey_menu.values():
            item.state = 1 if getattr(item, '_hotkey_value', None) == hk else 0
        print(f"[menubar] Hotkey: {hk}")

    def _switch_microphone(self, sender: Any) -> None:
        device = sender._mic_device
        if device == self.config.recording.device:
            return
        if device is None:
            self._set_config("recording.device", "")
        else:
            self._set_config("recording.device", device)
        self.config.recording.device = device
        self._app.recorder.device = device
        label = device or "System Default"
        self._mic_menu.title = f"Microphone: {label}"
        for item in self._mic_menu.values():
            item.state = 1 if getattr(item, "_mic_device", object()) == device else 0
        print(f"[menubar] Microphone: {label}")

    def _on_volume_slide(self, sender: Any) -> None:
        import time as _time
        pct = int(sender.value)
        vol = pct / 100.0
        self._app.config.audio_feedback.volume = vol
        self.config.audio_feedback.volume = vol
        self._volume_menu.title = f"Volume: {pct}%"
        now = _time.monotonic()
        # Debounce: only persist and preview after slider settles (0.3s)
        self._volume_last_change = now

        def _persist():
            _time.sleep(0.3)
            if self._volume_last_change == now:
                self._set_config("audio_feedback.volume", str(vol))
                self._app.play_beep(self._app.config.audio_feedback.start_frequency)
                print(f"[menubar] Volume: {pct}%")

        threading.Thread(target=_persist, daemon=True).start()

    def _toggle_text_commands(self, _sender: Any) -> None:
        current = self.config.text_commands.enabled
        new_val = not current
        self._set_config("text_commands.enabled", "true" if new_val else "false")
        self.config.text_commands.enabled = new_val
        self._app.cleaner.text_commands = new_val
        self._textcmds_item.title = f"Text Commands: {'on' if new_val else 'off'}"
        print(f"[menubar] Text Commands: {'on' if new_val else 'off'}")

    def _toggle_auto_send(self, _sender: Any) -> None:
        current = self.config.paste.auto_send
        new_val = not current
        self._set_config("paste.auto_send", "true" if new_val else "false")
        self.config.paste.auto_send = new_val
        self._app.config.paste.auto_send = new_val
        self._autosend_item.title = f"Auto-Send: {'on' if new_val else 'off'}"
        print(f"[menubar] Auto-Send: {'on' if new_val else 'off'}")

    def _toggle_audio_control(self, _sender: Any) -> None:
        current = self.config.audio_control.enabled
        new_val = not current
        self._set_config("audio_control.enabled", "true" if new_val else "false")
        self.config.audio_control.enabled = new_val
        self._app.audio_controller._enabled = new_val
        self._audioctrl_item.title = f"Audio Control: {'on' if new_val else 'off'}"
        print(f"[menubar] Audio Control: {'on' if new_val else 'off'}")

    def _toggle_failover(self, _sender: Any) -> None:
        current = self.config.whisper.failover
        new_val = not current
        self._set_config("whisper.failover", "true" if new_val else "false")
        self.config.whisper.failover = new_val
        self._app.config.whisper.failover = new_val
        self._failover_item.title = f"Failover: {'on' if new_val else 'off'}"
        print(f"[menubar] Failover: {'on' if new_val else 'off'}")

    def _build_recording_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("Recording")
        self._min_dur_item = rumps.MenuItem(
            f"Min Duration: {self.config.recording.min_duration}s",
            callback=self._edit_min_duration,
        )
        self._max_dur_item = rumps.MenuItem(
            f"Max Duration: {self.config.recording.max_duration}s",
            callback=self._edit_max_duration,
        )
        self._timeout_item = rumps.MenuItem(
            f"Timeout: {self.config.whisper.timeout_seconds}s",
            callback=self._edit_timeout,
        )
        menu.add(self._min_dur_item)
        menu.add(self._max_dur_item)
        menu.add(self._timeout_item)
        return menu

    def _prompt_float(self, title: str, message: str, current: float) -> float | None:
        """Prompt for a float value. Returns None if cancelled or invalid."""
        response = rumps.Window(
            title=title,
            message=message,
            default_text=str(current),
            ok="Save",
            cancel="Cancel",
        ).run()
        if not response.clicked:
            return None
        try:
            val = float(response.text.strip())
            if val <= 0:
                rumps.notification("whisper-dic", "Invalid Value", "Must be a positive number.")
                return None
            return val
        except ValueError:
            rumps.notification("whisper-dic", "Invalid Value", "Enter a number (e.g. 0.3).")
            return None

    def _edit_min_duration(self, _sender: Any) -> None:
        cur = self.config.recording.min_duration
        val = self._prompt_float("Min Duration", "Minimum recording duration in seconds:", cur)
        if val is not None:
            self._set_config("recording.min_duration", str(val))
            self.config.recording.min_duration = val
            self._app.config.recording.min_duration = val
            self._min_dur_item.title = f"Min Duration: {val}s"

    def _edit_max_duration(self, _sender: Any) -> None:
        cur = self.config.recording.max_duration
        val = self._prompt_float("Max Duration", "Maximum recording duration in seconds:", cur)
        if val is not None:
            self._set_config("recording.max_duration", str(val))
            self.config.recording.max_duration = val
            self._app.config.recording.max_duration = val
            self._max_dur_item.title = f"Max Duration: {val}s"

    def _edit_timeout(self, _sender: Any) -> None:
        val = self._prompt_float("Timeout", "Transcription timeout in seconds:", self.config.whisper.timeout_seconds)
        if val is not None:
            self._set_config("whisper.timeout_seconds", str(val))
            self.config.whisper.timeout_seconds = val
            self._app.config.whisper.timeout_seconds = val
            self._timeout_item.title = f"Timeout: {val}s"

    def _build_service_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("Service")
        menu.add(rumps.MenuItem("Install (Start at Login)", callback=self._install_service))
        menu.add(rumps.MenuItem("Uninstall", callback=self._uninstall_service))
        installed = "Yes" if _PLIST_PATH.exists() else "No"
        self._installed_item = rumps.MenuItem(f"Installed: {installed}")
        self._installed_item.set_callback(None)
        menu.add(self._installed_item)
        return menu

    def _install_service(self, _sender: Any) -> None:
        def _run():
            rc = command_install()
            if rc == 0:
                rumps.notification("whisper-dic", "Installed",
                                   "whisper-dic will start at login and auto-restart on crash.")
            else:
                rumps.notification("whisper-dic", "Install Failed",
                                   "Check the terminal for details.")
            self._installed_item.title = f"Installed: {'Yes' if _PLIST_PATH.exists() else 'No'}"
        threading.Thread(target=_run, daemon=True).start()

    def _uninstall_service(self, _sender: Any) -> None:
        result = rumps.alert(
            title="Uninstall whisper-dic?",
            message="This will remove whisper-dic from login items. It won't auto-start anymore.",
            ok="Uninstall",
            cancel="Cancel",
        )
        if result != 1:
            return

        def _run():
            rc = command_uninstall()
            if rc == 0:
                rumps.notification("whisper-dic", "Uninstalled",
                                   "whisper-dic removed from login items.")
            else:
                rumps.notification("whisper-dic", "Uninstall Failed",
                                   "Not currently installed.")
            self._installed_item.title = f"Installed: {'Yes' if _PLIST_PATH.exists() else 'No'}"
        threading.Thread(target=_run, daemon=True).start()

    def _version_item(self) -> rumps.MenuItem:
        version_file = Path(__file__).with_name("VERSION")
        version = version_file.read_text().strip() if version_file.exists() else "?"
        item = rumps.MenuItem(f"Version: {version}")
        item.set_callback(None)
        return item

    def _check_status(self, _sender: Any) -> None:
        def _run():
            provider = self.config.whisper.provider
            lang = self._app.active_language
            ok = self._app.transcriber.health_check()
            status = "reachable" if ok else "UNREACHABLE"
            rumps.notification(
                "whisper-dic", f"Provider: {provider} ({status})",
                f"Language: {lang} | Hotkey: {self.config.hotkey.key.replace('_', ' ')}",
            )
        threading.Thread(target=_run, daemon=True).start()

    def _view_logs(self, _sender: Any) -> None:
        log_path = Path.home() / "Library" / "Logs" / "whisper-dictation.log"
        if not log_path.exists():
            rumps.notification("whisper-dic", "No Logs", "No log file found yet.")
            return
        from AppKit import NSWorkspace
        NSWorkspace.sharedWorkspace().openFile_(str(log_path))

    def _on_config_changed(self, new_config: Any) -> None:
        """Called from watcher thread when config.toml changes externally."""
        from log import log
        log("config-watch", "Config changed externally, reloading...")
        old = self.config
        self.config = new_config

        if new_config.whisper.provider != old.whisper.provider:
            self._app.transcriber.close()
            self._app.transcriber = create_transcriber(new_config.whisper)
            self._provider_menu.title = f"Provider: {new_config.whisper.provider}"
            for item in self._provider_menu.values():
                item.state = 1 if item.title == new_config.whisper.provider else 0

        if new_config.whisper.language != old.whisper.language:
            self._app.set_language(new_config.whisper.language)
            display = LANG_NAMES.get(new_config.whisper.language, new_config.whisper.language)
            self._lang_menu.title = f"Language: {display}"
            for item in self._lang_menu.values():
                lang_code = item.title.split("(")[-1].rstrip(")") if "(" in item.title else ""
                item.state = 1 if lang_code == new_config.whisper.language else 0

        if new_config.hotkey.key != old.hotkey.key:
            self._app._listener.set_key(new_config.hotkey.key)
            self._hotkey_menu.title = f"Hotkey: {new_config.hotkey.key.replace('_', ' ')}"
            for item in self._hotkey_menu.values():
                item.state = 1 if getattr(item, "_hotkey_value", None) == new_config.hotkey.key else 0

        if new_config.audio_feedback.volume != old.audio_feedback.volume:
            self._app.config.audio_feedback.volume = new_config.audio_feedback.volume
            pct = int(new_config.audio_feedback.volume * 100)
            self._volume_menu.title = f"Volume: {pct}%"
            self._volume_slider.value = pct

        if new_config.paste.auto_send != old.paste.auto_send:
            self._app.config.paste.auto_send = new_config.paste.auto_send
            self._autosend_item.title = f"Auto-Send: {'on' if new_config.paste.auto_send else 'off'}"

        if new_config.text_commands.enabled != old.text_commands.enabled:
            self._app.cleaner.text_commands = new_config.text_commands.enabled
            self._textcmds_item.title = f"Text Commands: {'on' if new_config.text_commands.enabled else 'off'}"

        if new_config.audio_control.enabled != old.audio_control.enabled:
            self._app.audio_controller._enabled = new_config.audio_control.enabled
            self._audioctrl_item.title = f"Audio Control: {'on' if new_config.audio_control.enabled else 'off'}"

        if new_config.whisper.failover != old.whisper.failover:
            self._app.config.whisper.failover = new_config.whisper.failover
            self._failover_item.title = f"Failover: {'on' if new_config.whisper.failover else 'off'}"

        if new_config.recording.device != old.recording.device:
            self._app.recorder.device = new_config.recording.device
            label = new_config.recording.device or "System Default"
            self._mic_menu.title = f"Microphone: {label}"
            for item in self._mic_menu.values():
                item.state = 1 if getattr(item, "_mic_device", object()) == new_config.recording.device else 0

        rumps.notification("whisper-dic", "Config Reloaded", "Settings updated from config.toml")

    def _run_wizard(self, _timer: Any = None) -> None:
        """First-run setup wizard — guides through provider, API key, hotkey."""
        if _timer is not None:
            _timer.stop()

        # Step 1: Provider
        response = rumps.Window(
            title="Welcome to whisper-dic!",
            message=(
                "Choose your speech-to-text provider:\n\n"
                "  groq  — Cloud, fast, free tier (recommended)\n"
                "  local — Offline, needs whisper.cpp server\n\n"
                "Type 'groq' or 'local':"
            ),
            default_text="groq",
            ok="Next",
            cancel="Skip Setup",
        ).run()

        if response.clicked:
            provider = response.text.strip().lower()
            if provider not in ("groq", "local"):
                provider = "groq"
            self._set_config("whisper.provider", provider)

            # Step 2: API key (groq only)
            if provider == "groq":
                key_response = rumps.Window(
                    title="Groq API Key",
                    message="Get a free key at console.groq.com\nPaste it below:",
                    default_text="",
                    ok="Next",
                    cancel="Skip",
                    secure=True,
                ).run()
                if key_response.clicked and key_response.text.strip():
                    self._set_config("whisper.groq.api_key", key_response.text.strip())

            # Step 3: Hotkey
            hotkey_response = rumps.Window(
                title="Choose Hotkey",
                message=(
                    "Which key triggers dictation?\n\n"
                    "Options: left option, right option,\n"
                    "left command, right command,\n"
                    "left shift, right shift\n\n"
                    "Type the key name:"
                ),
                default_text="left option",
                ok="Finish",
                cancel="Use Default",
            ).run()
            if hotkey_response.clicked and hotkey_response.text.strip():
                hk = hotkey_response.text.strip().lower().replace(" ", "_")
                if hk in HOTKEY_OPTIONS:
                    self._set_config("hotkey.key", hk)

        # Reload config and start
        self._reload_after_wizard()

    def _reload_after_wizard(self) -> None:
        """Reload config with wizard choices and start dictation."""
        self.config = load_config(self.config_path)
        self._app.config = self.config

        # Update transcriber
        self._app.transcriber.close()
        self._app.transcriber = create_transcriber(self.config.whisper)

        # Update listener key
        self._app._listener.set_key(self.config.hotkey.key)

        # Update menus
        self._provider_menu.title = f"Provider: {self.config.whisper.provider}"
        for item in self._provider_menu.values():
            item.state = 1 if item.title == self.config.whisper.provider else 0

        hk = self.config.hotkey.key
        self._hotkey_menu.title = f"Hotkey: {hk.replace('_', ' ')}"
        for item in self._hotkey_menu.values():
            item.state = 1 if getattr(item, '_hotkey_value', None) == hk else 0

        # Start dictation
        thread = threading.Thread(target=self._start_dictation, daemon=True)
        thread.start()

    def _quit(self, _sender: Any) -> None:
        self._config_watcher.stop()
        self._app.stop()
        rumps.quit_application()

    # --- Startup ---

    def _check_permissions(self) -> None:
        """Check macOS permissions and show guidance if missing."""
        # Check Accessibility
        try:
            from ApplicationServices import AXIsProcessTrusted
            if not AXIsProcessTrusted():
                rumps.notification(
                    "whisper-dic", "Accessibility Permission Required",
                    "Open System Settings > Privacy & Security > Accessibility and add this app.",
                )
        except ImportError:
            pass

    def _start_dictation(self) -> None:
        self._check_permissions()

        if not self._app.startup_health_checks():
            provider = self.config.whisper.provider
            if provider == "groq" and not self.config.whisper.groq.api_key.strip():
                rumps.notification("whisper-dic", "Groq API Key Missing",
                                   "Run: whisper-dic set whisper.groq.api_key YOUR_KEY")
            elif provider == "local":
                rumps.notification("whisper-dic", "Local Whisper Unreachable",
                                   "Start your whisper.cpp server, then restart whisper-dic.")
            else:
                rumps.notification("whisper-dic", "Startup Failed",
                                   "Whisper provider is unreachable. Run: whisper-dic status")
            return

        self._app.start_listener()
        self._health_timer.start()
        self._config_watcher.start()
        key = self.config.hotkey.key.replace("_", " ")
        rumps.notification("whisper-dic", "Ready",
                           f"Hold {key} to dictate. Double-tap to cycle language.")
        print(f"[ready] Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")


def run_menubar(config_path: Path) -> int:
    from cli import _check_single_instance, _rotate_log_if_needed
    if not _check_single_instance():
        return 1
    _rotate_log_if_needed()

    # Hide Python from Dock — menu bar only
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    # Ensure config exists — copy template on first run
    first_run = False
    if not config_path.exists():
        example = config_path.parent / "config.example.toml"
        if example.exists():
            import shutil
            shutil.copy2(example, config_path)
            config_path.chmod(0o600)
            first_run = True
        else:
            print(f"[error] No config template at {example}")
            return 1

    app = DictationMenuBar(config_path)

    if first_run:
        # Schedule wizard on main thread after run loop starts
        wizard_timer = rumps.Timer(app._run_wizard, 0.5)
        wizard_timer.start()
    else:
        thread = threading.Thread(target=app._start_dictation, daemon=True)
        thread.start()

    def _handle_signal(signum: int, _frame: Any) -> None:
        app._app.stop()
        rumps.quit_application()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app.run()
    return 0
