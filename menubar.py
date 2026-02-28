"""macOS menu bar integration for whisper-dic."""

from __future__ import annotations

import signal
import threading
from pathlib import Path

import rumps

from dictation import DictationApp, load_config

LANG_NAMES = {
    "en": "English", "nl": "Dutch", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ru": "Russian",
    "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "auto": "Auto-detect",
    "ar": "Arabic", "hi": "Hindi", "pl": "Polish", "sv": "Swedish",
    "tr": "Turkish", "uk": "Ukrainian", "da": "Danish", "no": "Norwegian",
}


class DictationMenuBar(rumps.App):
    def __init__(self, config_path: Path) -> None:
        super().__init__("", quit_button=None)
        self.icon = None
        self.title = "\U0001f3a4"  # microphone emoji

        self.config_path = config_path
        self.config = load_config(config_path)

        self._app = DictationApp(self.config)
        self._app.on_state_change = self._on_state_change

        self._status_item = rumps.MenuItem("Status: Idle")
        self._status_item.set_callback(None)

        active_lang = self._app._languages[self._app._lang_index]
        display = LANG_NAMES.get(active_lang, active_lang)
        self._lang_item = rumps.MenuItem(f"Language: {display} ({active_lang})")
        self._lang_item.set_callback(None)

        self._provider_item = rumps.MenuItem(f"Provider: {self.config.whisper.provider}")
        self._provider_item.set_callback(None)

        key = self.config.hotkey.key.replace("_", " ")
        self._hotkey_item = rumps.MenuItem(f"Hotkey: {key}")
        self._hotkey_item.set_callback(None)

        tc_state = "on" if self.config.text_commands.enabled else "off"
        self._textcmds_item = rumps.MenuItem(f"Text Commands: {tc_state}")
        self._textcmds_item.set_callback(None)

        self.menu = [
            self._status_item,
            self._lang_item,
            None,  # separator
            self._provider_item,
            self._hotkey_item,
            self._textcmds_item,
            None,  # separator
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _on_state_change(self, state: str, detail: str) -> None:
        if state == "recording":
            self.title = "\U0001f534"  # red circle
            self._status_item.title = "Status: Recording..."
        elif state == "transcribing":
            self.title = "\u23f3"  # hourglass
            self._status_item.title = "Status: Transcribing..."
        elif state == "idle":
            self.title = "\U0001f3a4"  # microphone
            self._status_item.title = "Status: Idle"
        elif state == "language_changed":
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._lang_item.title = f"Language: {detail}"

    def _quit(self, _sender) -> None:
        self._app.stop()
        rumps.quit_application()

    def _start_dictation(self) -> None:
        if not self._app.startup_health_checks():
            rumps.notification(
                title="whisper-dic",
                subtitle="Startup Failed",
                message="Whisper provider is unreachable.",
            )
            return

        self._app._listener.start()
        key = self.config.hotkey.key.replace("_", " ")
        print(f"[ready] Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")


def run_menubar(config_path: Path) -> int:
    app = DictationMenuBar(config_path)

    # Start dictation listener in background thread
    thread = threading.Thread(target=app._start_dictation, daemon=True)
    thread.start()

    def _handle_signal(signum: int, _frame) -> None:
        app._app.stop()
        rumps.quit_application()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app.run()
    return 0
