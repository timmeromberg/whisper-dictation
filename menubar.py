"""macOS menu bar integration for whisper-dic."""

from __future__ import annotations

import signal
import threading
from pathlib import Path

import rumps

from dictation import (
    DictationApp, LANG_NAMES, load_config, set_config_value, create_transcriber,
    command_install, command_uninstall, _PLIST_PATH,
)

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

        # --- Status (read-only) ---
        self._status_item = rumps.MenuItem("Status: Idle")
        self._status_item.set_callback(None)

        # --- Language submenu ---
        active_lang = self._app.active_language
        display = LANG_NAMES.get(active_lang, active_lang)
        self._lang_menu = rumps.MenuItem(f"Language: {display}")
        for lang in self._app.languages:
            name = LANG_NAMES.get(lang, lang)
            item = rumps.MenuItem(f"{name} ({lang})", callback=self._switch_language)
            if lang == active_lang:
                item.state = 1
            self._lang_menu.add(item)

        # --- Provider submenu ---
        self._provider_menu = rumps.MenuItem(f"Provider: {self.config.whisper.provider}")
        for p in PROVIDER_OPTIONS:
            item = rumps.MenuItem(p, callback=self._switch_provider)
            if p == self.config.whisper.provider:
                item.state = 1
            self._provider_menu.add(item)

        # --- Hotkey submenu ---
        current_key = self.config.hotkey.key
        self._hotkey_menu = rumps.MenuItem(f"Hotkey: {current_key.replace('_', ' ')}")
        for hk in HOTKEY_OPTIONS:
            item = rumps.MenuItem(hk.replace("_", " "), callback=self._switch_hotkey)
            item._hotkey_value = hk
            if hk == current_key:
                item.state = 1
            self._hotkey_menu.add(item)

        # --- Volume slider ---
        vol_pct = int(self.config.audio_feedback.volume * 100)
        self._volume_menu = rumps.MenuItem(f"Volume: {vol_pct}%")
        self._volume_slider = rumps.SliderMenuItem(
            value=vol_pct,
            min_value=0,
            max_value=100,
            callback=self._on_volume_slide,
        )
        self._volume_menu.add(self._volume_slider)
        self._volume_last_change = 0.0

        # --- Text Commands toggle ---
        tc_on = self.config.text_commands.enabled
        self._textcmds_item = rumps.MenuItem(
            f"Text Commands: {'on' if tc_on else 'off'}",
            callback=self._toggle_text_commands,
        )

        # --- Auto-Send toggle ---
        as_on = self.config.paste.auto_send
        self._autosend_item = rumps.MenuItem(
            f"Auto-Send: {'on' if as_on else 'off'}",
            callback=self._toggle_auto_send,
        )

        # --- Audio Control toggle ---
        ac_on = self.config.audio_control.enabled
        self._audioctrl_item = rumps.MenuItem(
            f"Audio Control: {'on' if ac_on else 'off'}",
            callback=self._toggle_audio_control,
        )

        # --- How to Use ---
        key_display = self.config.hotkey.key.replace("_", " ")
        self._help_menu = rumps.MenuItem("How to Use")
        for label in [
            f"Hold {key_display} — dictate",
            f"Hold {key_display} + Ctrl — dictate + send",
            f"Hold {key_display} + Shift — voice command",
            f"Quick-tap {key_display} — cycle language",
        ]:
            item = rumps.MenuItem(label)
            item.set_callback(None)
            self._help_menu.add(item)

        # Voice commands submenu inside Help
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
        self._help_menu.add(voice_cmds)

        # Text commands submenu inside Help
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
        self._help_menu.add(text_cmds)

        # --- Build menu ---
        self.menu = [
            self._status_item,
            None,
            self._lang_menu,
            self._provider_menu,
            self._hotkey_menu,
            self._volume_menu,
            self._textcmds_item,
            self._autosend_item,
            self._audioctrl_item,
            None,
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

    # --- State callbacks ---

    _LEVEL_BARS = ["\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586", "\u2587", "\u2588"]

    def _on_state_change(self, state: str, detail: str) -> None:
        if state == "recording":
            self._is_recording = True
            self.title = "\U0001f534"
            self._status_item.title = "Status: Recording..."
            self._level_timer.start()
        elif state == "transcribing":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\u23f3"
            self._status_item.title = "Status: Transcribing..."
        elif state == "idle":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
        elif state == "language_changed":
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._lang_menu.title = f"Language: {detail}"
            # Update checkmarks
            new_lang = self._app.active_language
            for item in self._lang_menu.values():
                item.state = 1 if f"({new_lang})" in item.title else 0

    def _periodic_health_check(self, _timer) -> None:
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

    def _update_level(self, _timer) -> None:
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

    def _switch_language(self, sender) -> None:
        # Extract lang code from "English (en)"
        lang = sender.title.split("(")[-1].rstrip(")")
        if lang == self._app.active_language:
            return
        self._app.set_language(lang)
        display = LANG_NAMES.get(lang, lang)
        self._lang_menu.title = f"Language: {display}"
        for item in self._lang_menu.values():
            item.state = 1 if sender.title == item.title else 0
        set_config_value(self.config_path, "whisper.language", lang)
        print(f"[menubar] Language: {display} ({lang})")

    def _switch_provider(self, sender) -> None:
        provider = sender.title
        if provider == self.config.whisper.provider:
            return
        if provider == "groq" and not self.config.whisper.groq.api_key.strip():
            if not self._prompt_groq_key():
                return
        set_config_value(self.config_path, "whisper.provider", provider)
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
        set_config_value(self.config_path, "whisper.groq.api_key", response.text.strip())
        self.config = load_config(self.config_path)
        return True

    def _set_groq_key(self, _sender) -> None:
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

    def _switch_hotkey(self, sender) -> None:
        hk = sender._hotkey_value
        if hk == self.config.hotkey.key:
            return
        set_config_value(self.config_path, "hotkey.key", hk)
        self.config.hotkey.key = hk
        self._app.listener.set_key(hk)
        self._hotkey_menu.title = f"Hotkey: {hk.replace('_', ' ')}"
        for item in self._hotkey_menu.values():
            item.state = 1 if getattr(item, '_hotkey_value', None) == hk else 0
        print(f"[menubar] Hotkey: {hk}")

    def _on_volume_slide(self, sender) -> None:
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
                set_config_value(self.config_path, "audio_feedback.volume", str(vol))
                self._app.play_beep(self._app.config.audio_feedback.start_frequency)
                print(f"[menubar] Volume: {pct}%")

        threading.Thread(target=_persist, daemon=True).start()

    def _toggle_text_commands(self, _sender) -> None:
        current = self.config.text_commands.enabled
        new_val = not current
        set_config_value(self.config_path, "text_commands.enabled", "true" if new_val else "false")
        self.config.text_commands.enabled = new_val
        self._app.cleaner.text_commands = new_val
        self._textcmds_item.title = f"Text Commands: {'on' if new_val else 'off'}"
        print(f"[menubar] Text Commands: {'on' if new_val else 'off'}")

    def _toggle_auto_send(self, _sender) -> None:
        current = self.config.paste.auto_send
        new_val = not current
        set_config_value(self.config_path, "paste.auto_send", "true" if new_val else "false")
        self.config.paste.auto_send = new_val
        self._app.config.paste.auto_send = new_val
        self._autosend_item.title = f"Auto-Send: {'on' if new_val else 'off'}"
        print(f"[menubar] Auto-Send: {'on' if new_val else 'off'}")

    def _toggle_audio_control(self, _sender) -> None:
        current = self.config.audio_control.enabled
        new_val = not current
        set_config_value(self.config_path, "audio_control.enabled", "true" if new_val else "false")
        self.config.audio_control.enabled = new_val
        self._app.audio_controller._enabled = new_val
        self._audioctrl_item.title = f"Audio Control: {'on' if new_val else 'off'}"
        print(f"[menubar] Audio Control: {'on' if new_val else 'off'}")

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

    def _edit_min_duration(self, _sender) -> None:
        val = self._prompt_float("Min Duration", "Minimum recording duration in seconds:", self.config.recording.min_duration)
        if val is not None:
            set_config_value(self.config_path, "recording.min_duration", str(val))
            self.config.recording.min_duration = val
            self._app.config.recording.min_duration = val
            self._min_dur_item.title = f"Min Duration: {val}s"

    def _edit_max_duration(self, _sender) -> None:
        val = self._prompt_float("Max Duration", "Maximum recording duration in seconds:", self.config.recording.max_duration)
        if val is not None:
            set_config_value(self.config_path, "recording.max_duration", str(val))
            self.config.recording.max_duration = val
            self._app.config.recording.max_duration = val
            self._max_dur_item.title = f"Max Duration: {val}s"

    def _edit_timeout(self, _sender) -> None:
        val = self._prompt_float("Timeout", "Transcription timeout in seconds:", self.config.whisper.timeout_seconds)
        if val is not None:
            set_config_value(self.config_path, "whisper.timeout_seconds", str(val))
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

    def _install_service(self, _sender) -> None:
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

    def _uninstall_service(self, _sender) -> None:
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

    def _check_status(self, _sender) -> None:
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

    def _view_logs(self, _sender) -> None:
        log_path = Path.home() / "Library" / "Logs" / "whisper-dictation.log"
        if not log_path.exists():
            rumps.notification("whisper-dic", "No Logs", "No log file found yet.")
            return
        from AppKit import NSWorkspace
        NSWorkspace.sharedWorkspace().openFile_(str(log_path))

    def _quit(self, _sender) -> None:
        self._app.stop()
        rumps.quit_application()

    # --- Startup ---

    def _start_dictation(self) -> None:
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
        key = self.config.hotkey.key.replace("_", " ")
        rumps.notification("whisper-dic", "Ready",
                           f"Hold {key} to dictate. Tap to cycle language.")
        print(f"[ready] Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")


def run_menubar(config_path: Path) -> int:
    # Hide Python from Dock — menu bar only
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    app = DictationMenuBar(config_path)

    thread = threading.Thread(target=app._start_dictation, daemon=True)
    thread.start()

    def _handle_signal(signum: int, _frame) -> None:
        app._app.stop()
        rumps.quit_application()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app.run()
    return 0
