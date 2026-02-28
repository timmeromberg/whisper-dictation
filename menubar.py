"""macOS menu bar integration for whisper-dic."""

from __future__ import annotations

import signal
import threading
from pathlib import Path

import rumps

from dictation import DictationApp, load_config, set_config_value, create_transcriber

LANG_NAMES = {
    "en": "English", "nl": "Dutch", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "auto": "Auto-detect",
    "ar": "Arabic", "hi": "Hindi", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian", "da": "Danish", "no": "Norwegian",
}

PROVIDER_OPTIONS = ["local", "groq"]
LANGUAGE_OPTIONS = ["en", "auto", "nl", "de", "fr", "es", "ja", "zh", "ko", "pt", "it", "ru"]
HOTKEY_OPTIONS = ["left_option", "right_option", "left_command", "right_command", "left_shift", "right_shift"]
VOLUME_OPTIONS = ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0"]


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

        # --- Status (read-only) ---
        self._status_item = rumps.MenuItem("Status: Idle")
        self._status_item.set_callback(None)

        # --- Language submenu ---
        active_lang = self._app._languages[self._app._lang_index]
        display = LANG_NAMES.get(active_lang, active_lang)
        self._lang_menu = rumps.MenuItem(f"Language: {display}")
        for lang in self._app._languages:
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

        # --- Volume submenu ---
        current_vol = f"{int(self.config.audio_feedback.volume * 100)}%"
        self._volume_menu = rumps.MenuItem(f"Volume: {current_vol}")
        for v in VOLUME_OPTIONS:
            label = f"{int(float(v) * 100)}%"
            item = rumps.MenuItem(label, callback=self._switch_volume)
            item._vol_value = v
            if label == current_vol:
                item.state = 1
            self._volume_menu.add(item)

        # --- Text Commands toggle ---
        tc_on = self.config.text_commands.enabled
        self._textcmds_item = rumps.MenuItem(
            f"Text Commands: {'on' if tc_on else 'off'}",
            callback=self._toggle_text_commands,
        )

        # --- Build menu ---
        self.menu = [
            self._status_item,
            None,
            self._lang_menu,
            self._provider_menu,
            self._hotkey_menu,
            self._volume_menu,
            self._textcmds_item,
            None,
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
            new_lang = self._app._languages[self._app._lang_index]
            for item in self._lang_menu.values():
                item.state = 1 if f"({new_lang})" in item.title else 0

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
        if lang == self._app._languages[self._app._lang_index]:
            return
        if lang in self._app._languages:
            self._app._lang_index = self._app._languages.index(lang)
        self._app.transcriber.language = lang
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
            rumps.notification("whisper-dic", "Groq API key not set",
                               "Set it via: whisper-dic set whisper.groq.api_key YOUR_KEY")
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

    def _switch_hotkey(self, sender) -> None:
        hk = sender._hotkey_value
        if hk == self.config.hotkey.key:
            return
        set_config_value(self.config_path, "hotkey.key", hk)
        self._hotkey_menu.title = f"Hotkey: {hk.replace('_', ' ')}"
        for item in self._hotkey_menu.values():
            item.state = 1 if getattr(item, '_hotkey_value', None) == hk else 0
        rumps.notification("whisper-dic", "Hotkey Changed",
                           f"Restart whisper-dic to use: {hk.replace('_', ' ')}")
        print(f"[menubar] Hotkey: {hk} (restart required)")

    def _switch_volume(self, sender) -> None:
        vol = sender._vol_value
        set_config_value(self.config_path, "audio_feedback.volume", vol)
        self.config = load_config(self.config_path)
        self._app.config.audio_feedback.volume = float(vol)
        label = f"{int(float(vol) * 100)}%"
        self._volume_menu.title = f"Volume: {label}"
        for item in self._volume_menu.values():
            item.state = 1 if getattr(item, '_vol_value', None) == vol else 0
        print(f"[menubar] Volume: {label}")

    def _toggle_text_commands(self, _sender) -> None:
        current = self.config.text_commands.enabled
        new_val = not current
        set_config_value(self.config_path, "text_commands.enabled", "true" if new_val else "false")
        self.config.text_commands.enabled = new_val
        self._app.cleaner.text_commands = new_val
        self._textcmds_item.title = f"Text Commands: {'on' if new_val else 'off'}"
        print(f"[menubar] Text Commands: {'on' if new_val else 'off'}")

    def _quit(self, _sender) -> None:
        self._app.stop()
        rumps.quit_application()

    # --- Startup ---

    def _start_dictation(self) -> None:
        if not self._app.startup_health_checks():
            rumps.notification("whisper-dic", "Startup Failed",
                               "Whisper provider is unreachable.")
            return

        self._app._listener.start()
        key = self.config.hotkey.key.replace("_", " ")
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
