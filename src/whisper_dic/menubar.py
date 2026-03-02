"""macOS menu bar integration for whisper-dic."""

from __future__ import annotations

import faulthandler
import os
import signal
import threading
import time
from pathlib import Path
from typing import Any

import rumps
import sounddevice as sd
from PyObjCTools.AppHelper import callAfter

from .cli import _PLIST_PATH, command_install, command_uninstall
from .config import LANG_NAMES, ConfigWatcher, load_config, set_config_value
from .dictation import DictationApp
from .hotkey import NSEventHotkeyListener
from .overlay import PreviewOverlay, RecordingOverlay
from .transcriber import create_transcriber

faulthandler.enable()

PROVIDER_OPTIONS = ["local", "groq"]
LANGUAGE_OPTIONS = ["en", "auto", "nl", "de", "fr", "es", "ja", "zh", "ko", "pt", "it", "ru"]
HOTKEY_OPTIONS = ["left_option", "right_option", "left_command", "right_command", "left_shift", "right_shift"]
_SMOKE_NO_INPUT_ENV = "WHISPER_DIC_SMOKE_NO_INPUT"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


class DictationMenuBar(rumps.App):
    def __init__(self, config_path: Path) -> None:
        super().__init__("", quit_button=None)
        self.icon = None
        self.title = "\U0001f3a4"  # microphone emoji

        self.config_path = config_path
        self.config = load_config(config_path)

        self._app = DictationApp(self.config, listener_class=NSEventHotkeyListener)
        self._app.on_state_change = self._on_state_change
        self._is_recording = False
        self._level_timer = rumps.Timer(self._update_level, 0.15)
        self._health_timer = rumps.Timer(self._periodic_health_check, 60)
        self._device_timer = rumps.Timer(self._check_device_changes, 5)
        self._known_input_devices: set[str] = self._get_input_device_names()
        self._provider_healthy = True
        self._health_notified = False
        self._config_watcher = ConfigWatcher(config_path, self._on_config_changed)
        self._overlay = RecordingOverlay()
        self._preview_overlay = PreviewOverlay()
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
        sp_on = self.config.recording.streaming_preview
        self._preview_item = rumps.MenuItem(
            f"Live Preview: {'on' if sp_on else 'off'}",
            callback=self._toggle_preview,
        )
        self._rewrite_menu = self._build_rewrite_menu()
        self._help_menu = self._build_help_menu()
        self._accessibility_menu = self._build_accessibility_menu()
        self._history_menu = rumps.MenuItem("History")
        self._rebuild_history_menu()
        self._apply_overlay_accessibility()

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
            self._preview_item,
            self._rewrite_menu,
            None,
            self._history_menu,
            self._build_recording_menu(),
            self._accessibility_menu,
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

    def _build_toggle_items(
        self,
    ) -> tuple[rumps.MenuItem, rumps.MenuItem, rumps.MenuItem, rumps.MenuItem]:
        tc_on = self.config.text_commands.enabled
        textcmds = rumps.MenuItem(f"Text Commands: {'on' if tc_on else 'off'}", callback=self._toggle_text_commands)

        as_on = self.config.paste.auto_send
        autosend = rumps.MenuItem(f"Auto-Send: {'on' if as_on else 'off'}", callback=self._toggle_auto_send)

        ac_on = self.config.audio_control.enabled
        audioctrl = rumps.MenuItem(f"Audio Control: {'on' if ac_on else 'off'}", callback=self._toggle_audio_control)

        fo_on = self.config.whisper.failover
        failover = rumps.MenuItem(f"Failover: {'on' if fo_on else 'off'}", callback=self._toggle_failover)

        return textcmds, autosend, audioctrl, failover

    def _build_rewrite_menu(self) -> rumps.MenuItem:
        from .rewriter import REWRITE_PRESETS

        rw = self.config.rewrite
        label = "on" if rw.enabled else "off"
        menu = rumps.MenuItem(f"AI Rewrite: {label}")

        self._rewrite_toggle = rumps.MenuItem(
            f"Enabled: {'yes' if rw.enabled else 'no'}",
            callback=self._toggle_rewrite,
        )
        menu.add(self._rewrite_toggle)
        menu.add(None)

        # Per-app context toggles (shown first — they take priority)
        menu.add(self._build_context_menu())
        menu.add(None)

        # Default mode (fallback for unrecognized apps)
        default_label = rumps.MenuItem("Default Mode (other apps)")
        default_label.set_callback(None)
        menu.add(default_label)

        self._rewrite_mode_items: dict[str, rumps.MenuItem] = {}
        for mode, (description, _prompt) in REWRITE_PRESETS.items():
            item = rumps.MenuItem(f"{mode.title()} — {description}", callback=self._switch_rewrite_mode)
            item._rewrite_mode = mode  # type: ignore[attr-defined]
            item.state = 1 if rw.mode == mode else 0
            self._rewrite_mode_items[mode] = item
            menu.add(item)

        custom_item = rumps.MenuItem("Custom — use your own prompt", callback=self._switch_rewrite_mode)
        custom_item._rewrite_mode = "custom"  # type: ignore[attr-defined]
        custom_item.state = 1 if rw.mode == "custom" else 0
        self._rewrite_mode_items["custom"] = custom_item
        menu.add(custom_item)

        menu.add(None)
        menu.add(rumps.MenuItem("Edit Custom Prompt...", callback=self._edit_rewrite_prompt))
        menu.add(rumps.MenuItem("Change Model...", callback=self._edit_rewrite_model))

        return menu

    def _build_context_menu(self) -> rumps.MenuItem:
        from .app_context import CATEGORIES

        menu = rumps.MenuItem("Per-App Context")
        self._context_items: dict[str, rumps.MenuItem] = {}
        for cat in CATEGORIES:
            cfg = self.config.rewrite.contexts.get(cat)
            enabled = cfg.enabled if cfg else True
            item = rumps.MenuItem(
                f"{cat.title()}: {'on' if enabled else 'off'}",
                callback=self._toggle_context,
            )
            item._context_category = cat  # type: ignore[attr-defined]
            self._context_items[cat] = item
            menu.add(item)
        return menu

    def _toggle_context(self, sender: Any) -> None:
        cat = sender._context_category  # type: ignore[attr-defined]
        cfg = self.config.rewrite.contexts.get(cat)
        if cfg is None:
            return
        new_val = not cfg.enabled
        cfg.enabled = new_val
        self._app.config.rewrite.contexts[cat].enabled = new_val
        self._set_config(f"rewrite.contexts.{cat}.enabled", str(new_val).lower())
        sender.title = f"{cat.title()}: {'on' if new_val else 'off'}"
        print(f"[menubar] Context {cat}: {'on' if new_val else 'off'}")

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

    def _build_accessibility_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("Accessibility")
        reduced = self.config.overlay.reduced_motion
        contrast = self.config.overlay.high_contrast
        scale = self.config.overlay.font_scale

        self._overlay_reduce_item = rumps.MenuItem(
            f"Reduced Motion: {'on' if reduced else 'off'}",
            callback=self._toggle_reduced_motion,
        )
        self._overlay_contrast_item = rumps.MenuItem(
            f"High Contrast: {'on' if contrast else 'off'}",
            callback=self._toggle_high_contrast,
        )
        menu.add(self._overlay_reduce_item)
        menu.add(self._overlay_contrast_item)
        menu.add(None)

        self._overlay_scale_menu = rumps.MenuItem(f"Text Size: {int(scale * 100)}%")
        self._overlay_scale_items: dict[float, rumps.MenuItem] = {}
        for value in (0.85, 1.0, 1.25, 1.5):
            item = rumps.MenuItem(f"{int(value * 100)}%", callback=self._switch_overlay_scale)
            item._overlay_scale = value  # type: ignore[attr-defined]
            item.state = 1 if abs(value - scale) < 1e-6 else 0
            self._overlay_scale_items[value] = item
            self._overlay_scale_menu.add(item)
        menu.add(self._overlay_scale_menu)
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
        text = str(getattr(sender, "_history_text", "")).strip()
        if not text:
            self._notify("Copy Failed", "History entry is empty.")
            return
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=2)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            self._notify("Copy Failed", "Could not copy entry to clipboard.")
            return
        self._notify("Copied", text[:80])

    def _clear_history(self, _sender: Any) -> None:
        self._app.history.clear()
        self._rebuild_history_menu()

    # --- Config helpers ---

    def _set_config(self, key: str, value: str) -> None:
        """Write a config value and mark the write to avoid reload loop."""
        set_config_value(self.config_path, key, value)
        self._config_watcher.mark_written()

    def _notify(self, subtitle: str, message: str) -> None:
        """Thread-safe user notification."""
        callAfter(rumps.notification, "whisper-dic", subtitle, message)

    # --- State callbacks ---

    _LEVEL_BARS = ["\u2581", "\u2582", "\u2583", "\u2584", "\u2585", "\u2586", "\u2587", "\u2588"]

    def _update_preview_badges(self) -> None:
        """Sync preview overlay badges with current config state."""
        badges: list[str] = []
        badges.append(self.config.whisper.language.upper())
        if self.config.rewrite.enabled:
            badges.append("AI Rewrite")
        if self.config.paste.auto_send:
            badges.append("Auto-Send")
        self._preview_overlay.set_badges(badges)

    def _on_state_change(self, state: str, detail: str) -> None:
        """Thread-safe state callback entrypoint from DictationApp."""
        callAfter(self._on_state_change_main, state, detail)

    def _on_state_change_main(self, state: str, detail: str) -> None:
        """Main-thread state handler. Mutates rumps/AppKit state safely."""
        if state == "recording":
            self._is_recording = True
            self.title = "\U0001f534"
            self._status_item.title = "Status: Recording..."
            self._level_timer.start()
            self._overlay.show_recording()
            self._update_preview_badges()
            self._preview_overlay.set_recording_start(time.monotonic())
        elif state == "transcribing":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\u23f3"
            self._status_item.title = "Status: Transcribing..."
            self._overlay.show_transcribing()
        elif state == "preview":
            if detail:
                self._preview_overlay.show(detail)
            else:
                self._preview_overlay.hide()
        elif state == "idle":
            self._is_recording = False
            self._level_timer.stop()
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._rebuild_history_menu()
            self._overlay.hide()
            self._preview_overlay.hide()
        elif state == "language_changed":
            new_lang = self._app.active_language
            self.title = "\U0001f3a4"
            self._status_item.title = "Status: Idle"
            self._lang_menu.title = f"Language: {detail}"
            for item in self._lang_menu.values():
                item.state = 1 if f"({new_lang})" in item.title else 0

    def _periodic_health_check(self, _timer: Any) -> None:
        def _run():
            ok = self._app.transcriber_health_check()
            if not ok and self._provider_healthy:
                def _update_down():
                    self._provider_healthy = False
                    self._status_item.title = "Status: Provider Unreachable"
                    self.title = "\u26a0\ufe0f"  # warning emoji
                    if not self._health_notified:
                        provider = self.config.whisper.provider
                        self._notify("Provider Unreachable", f"{provider} is not responding. Dictation may fail.")
                        self._health_notified = True
                callAfter(_update_down)
            elif ok and not self._provider_healthy:
                def _update_up():
                    self._provider_healthy = True
                    self._health_notified = False
                    if not self._is_recording:
                        self._status_item.title = "Status: Idle"
                        self.title = "\U0001f3a4"
                    self._notify("Provider Online", "Connection restored. Dictation is ready.")
                callAfter(_update_up)
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

    @staticmethod
    def _get_input_device_names() -> set[str]:
        try:
            return {str(d["name"]) for d in sd.query_devices() if d["max_input_channels"] > 0}  # type: ignore[index]
        except Exception:
            return set()

    def _check_device_changes(self, _timer: Any) -> None:
        current = self._get_input_device_names()
        if current != self._known_input_devices:
            self._known_input_devices = current
            self._rebuild_mic_menu()

    def _rebuild_mic_menu(self) -> None:
        """Rebuild microphone submenu items to reflect connected devices."""
        current = self.config.recording.device
        self._mic_menu.clear()
        default_item = rumps.MenuItem("System Default", callback=self._switch_microphone)
        default_item._mic_device = None  # type: ignore[attr-defined]
        if current is None:
            default_item.state = 1
        self._mic_menu.add(default_item)
        for name in sorted(self._known_input_devices):
            item = rumps.MenuItem(name, callback=self._switch_microphone)
            item._mic_device = name  # type: ignore[attr-defined]
            if name == current:
                item.state = 1
            self._mic_menu.add(item)
        label = current or "System Default"
        self._mic_menu.title = f"Microphone: {label}"

    # --- Setting actions ---

    def _apply_overlay_accessibility(self) -> None:
        ov = self.config.overlay
        self._overlay.configure_accessibility(
            reduced_motion=ov.reduced_motion,
            high_contrast=ov.high_contrast,
        )
        self._preview_overlay.configure_accessibility(
            reduced_motion=ov.reduced_motion,
            high_contrast=ov.high_contrast,
            font_scale=ov.font_scale,
        )

    def _toggle_reduced_motion(self, _sender: Any) -> None:
        new_val = not self.config.overlay.reduced_motion
        self._set_config("overlay.reduced_motion", "true" if new_val else "false")
        self.config.overlay.reduced_motion = new_val
        self._app.config.overlay.reduced_motion = new_val
        self._overlay_reduce_item.title = f"Reduced Motion: {'on' if new_val else 'off'}"
        self._apply_overlay_accessibility()
        print(f"[menubar] Reduced Motion: {'on' if new_val else 'off'}")

    def _toggle_high_contrast(self, _sender: Any) -> None:
        new_val = not self.config.overlay.high_contrast
        self._set_config("overlay.high_contrast", "true" if new_val else "false")
        self.config.overlay.high_contrast = new_val
        self._app.config.overlay.high_contrast = new_val
        self._overlay_contrast_item.title = f"High Contrast: {'on' if new_val else 'off'}"
        self._apply_overlay_accessibility()
        print(f"[menubar] High Contrast: {'on' if new_val else 'off'}")

    def _switch_overlay_scale(self, sender: Any) -> None:
        scale = float(sender._overlay_scale)
        if abs(scale - self.config.overlay.font_scale) < 1e-6:
            return
        self._set_config("overlay.font_scale", str(scale))
        self.config.overlay.font_scale = scale
        self._app.config.overlay.font_scale = scale
        self._overlay_scale_menu.title = f"Text Size: {int(scale * 100)}%"
        for value, item in self._overlay_scale_items.items():
            item.state = 1 if abs(value - scale) < 1e-6 else 0
        self._apply_overlay_accessibility()
        print(f"[menubar] Text Size: {int(scale * 100)}%")

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
        self._app.replace_transcriber(create_transcriber(self.config.whisper))
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
                self._app.replace_transcriber(create_transcriber(self.config.whisper))
                threading.Thread(target=self._check_provider_health, daemon=True).start()
            self._notify("API Key Updated", "Groq API key saved.")

    def _check_provider_health(self) -> None:
        """Run a health check and notify the user of the result."""
        provider = self.config.whisper.provider
        try:
            ok = self._app.transcriber_health_check()
        except Exception:
            ok = False
        if ok:
            self._notify("Connection Verified", f"{provider} provider is reachable.")
        else:
            self._notify("Connection Failed", f"{provider} provider is unreachable. Check your settings.")

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
        from .audio_control import AudioController
        current = self.config.audio_control.enabled
        new_val = not current
        self._set_config("audio_control.enabled", "true" if new_val else "false")
        self.config.audio_control.enabled = new_val
        # Recreate controller so devices are set up when toggling on
        self._app.audio_controller = AudioController(self.config.audio_control)
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

    def _toggle_preview(self, _sender: Any) -> None:
        current = self.config.recording.streaming_preview
        new_val = not current
        self._set_config("recording.streaming_preview", "true" if new_val else "false")
        self.config.recording.streaming_preview = new_val
        self._app.config.recording.streaming_preview = new_val
        self._preview_item.title = f"Live Preview: {'on' if new_val else 'off'}"
        print(f"[menubar] Live Preview: {'on' if new_val else 'off'}")

    def _toggle_rewrite(self, _sender: Any) -> None:
        current = self.config.rewrite.enabled
        new_val = not current
        self._set_config("rewrite.enabled", "true" if new_val else "false")
        self.config.rewrite.enabled = new_val
        self._app.config.rewrite.enabled = new_val

        if new_val:
            self._recreate_rewriter()
            if self._app._rewriter is None:
                return  # API key missing, already reverted
        else:
            if self._app._rewriter is not None:
                self._app._rewriter.close()
                self._app._rewriter = None

        self._update_rewrite_labels()
        print(f"[menubar] AI Rewrite: {'on' if new_val else 'off'}")

    def _switch_rewrite_mode(self, sender: Any) -> None:
        mode = sender._rewrite_mode
        if mode == self.config.rewrite.mode:
            return
        self._set_config("rewrite.mode", mode)
        self.config.rewrite.mode = mode
        self._app.config.rewrite.mode = mode

        # Update checkmarks
        for m, item in self._rewrite_mode_items.items():
            item.state = 1 if m == mode else 0

        # Recreate rewriter with new prompt if enabled
        if self.config.rewrite.enabled:
            self._recreate_rewriter()

        print(f"[menubar] Rewrite mode: {mode}")

    def _edit_rewrite_prompt(self, _sender: Any) -> None:
        current = self.config.rewrite.prompt
        response = rumps.Window(
            title="Custom Rewrite Prompt",
            message="Enter the system prompt the LLM will use to rewrite your dictation:",
            default_text=current,
            ok="Save",
            cancel="Cancel",
        ).run()
        if not response.clicked:
            return
        new_prompt = response.text.strip()
        if not new_prompt:
            return
        self._set_config("rewrite.prompt", new_prompt)
        self.config.rewrite.prompt = new_prompt
        self._app.config.rewrite.prompt = new_prompt

        # Auto-switch to custom mode
        if self.config.rewrite.mode != "custom":
            self._set_config("rewrite.mode", "custom")
            self.config.rewrite.mode = "custom"
            self._app.config.rewrite.mode = "custom"
            for m, item in self._rewrite_mode_items.items():
                item.state = 1 if m == "custom" else 0

        if self.config.rewrite.enabled:
            self._recreate_rewriter()

        print("[menubar] Custom rewrite prompt updated")

    def _edit_rewrite_model(self, _sender: Any) -> None:
        current = self.config.rewrite.model
        response = rumps.Window(
            title="Rewrite Model",
            message="Enter the Groq model ID for rewriting:",
            default_text=current,
            ok="Save",
            cancel="Cancel",
        ).run()
        if not response.clicked or not response.text.strip():
            return
        new_model = response.text.strip()
        self._set_config("rewrite.model", new_model)
        self.config.rewrite.model = new_model
        self._app.config.rewrite.model = new_model

        if self.config.rewrite.enabled:
            self._recreate_rewriter()

        print(f"[menubar] Rewrite model: {new_model}")

    def _recreate_rewriter(self, notify_missing_key: bool = True) -> None:
        """Create or recreate the rewriter with current config. Reverts on missing API key."""
        from .rewriter import Rewriter, prompt_for_mode

        api_key = self.config.whisper.groq.api_key.strip()
        if not api_key:
            if notify_missing_key:
                self._notify("AI Rewrite", "Groq API key required. Set it first.")
            self.config.rewrite.enabled = False
            self._app.config.rewrite.enabled = False
            self._set_config("rewrite.enabled", "false")
            callAfter(self._update_rewrite_labels)
            return

        if self._app._rewriter is not None:
            self._app._rewriter.close()
        self._app._rewriter = Rewriter(
            api_key=api_key,
            model=self.config.rewrite.model,
            prompt=prompt_for_mode(self.config.rewrite.mode, self.config.rewrite.prompt),
        )

    def _update_rewrite_labels(self) -> None:
        """Sync menu labels with current rewrite config state."""
        enabled = self.config.rewrite.enabled
        self._rewrite_menu.title = f"AI Rewrite: {'on' if enabled else 'off'}"
        self._rewrite_toggle.title = f"Enabled: {'yes' if enabled else 'no'}"

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
        self._preview_interval_item = rumps.MenuItem(
            f"Preview Interval: {self.config.recording.preview_interval}s",
            callback=self._edit_preview_interval,
        )
        self._preview_provider_menu = self._build_preview_provider_menu()
        menu.add(self._min_dur_item)
        menu.add(self._max_dur_item)
        menu.add(self._timeout_item)
        menu.add(self._preview_interval_item)
        menu.add(self._preview_provider_menu)
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
                self._notify("Invalid Value", "Must be a positive number.")
                return None
            return val
        except ValueError:
            self._notify("Invalid Value", "Enter a number (e.g. 0.3).")
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

    def _edit_preview_interval(self, _sender: Any) -> None:
        cur = self.config.recording.preview_interval
        val = self._prompt_float(
            "Preview Interval",
            "Seconds between live preview updates (0.1–30.0).\n"
            "Lower = more responsive but uses more API calls.",
            cur,
        )
        if val is not None:
            val = max(0.1, min(30.0, val))
            self._set_config("recording.preview_interval", str(val))
            self.config.recording.preview_interval = val
            self._app.config.recording.preview_interval = val
            self._preview_interval_item.title = f"Preview Interval: {val}s"

    def _build_preview_provider_menu(self) -> rumps.MenuItem:
        current = self.config.recording.preview_provider or self.config.whisper.provider
        menu = rumps.MenuItem(f"Preview Provider: {current}")
        for option in PROVIDER_OPTIONS:
            item = rumps.MenuItem(option, callback=self._switch_preview_provider)
            item.state = 1 if option == current else 0
            menu.add(item)
        return menu

    def _switch_preview_provider(self, sender: Any) -> None:
        provider = sender.title
        current = self.config.recording.preview_provider or self.config.whisper.provider
        if provider == current:
            return
        if provider == "groq" and not self.config.whisper.groq.api_key.strip():
            if not self._prompt_groq_key():
                return
        self._set_config("recording.preview_provider", provider)
        self.config.recording.preview_provider = provider
        self._app.config.recording.preview_provider = provider
        # Force preview transcriber recreation on next dictation
        self._app.reset_preview_transcriber()
        self._preview_provider_menu.title = f"Preview Provider: {provider}"
        for item in self._preview_provider_menu.values():
            item.state = 1 if item.title == provider else 0
        print(f"[menubar] Preview Provider: {provider}")

    def _build_service_menu(self) -> rumps.MenuItem:
        menu = rumps.MenuItem("Service")
        menu.add(rumps.MenuItem("Install (Start at Login)", callback=self._install_service))
        menu.add(rumps.MenuItem("Uninstall", callback=self._uninstall_service))
        installed = "Yes" if self._service_installed() else "No"
        self._installed_item = rumps.MenuItem(f"Installed: {installed}")
        self._installed_item.set_callback(None)
        menu.add(self._installed_item)
        return menu

    @staticmethod
    def _service_installed() -> bool:
        return _PLIST_PATH is not None and _PLIST_PATH.exists()

    def _install_service(self, _sender: Any) -> None:
        def _run():
            rc = command_install()
            installed = "Yes" if self._service_installed() else "No"

            def _ui() -> None:
                if rc == 0:
                    self._notify("Installed", "whisper-dic will start at login and auto-restart on crash.")
                else:
                    self._notify("Install Failed", "Check the terminal for details.")
                self._installed_item.title = f"Installed: {installed}"

            callAfter(_ui)

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
            installed = "Yes" if self._service_installed() else "No"

            def _ui() -> None:
                if rc == 0:
                    self._notify("Uninstalled", "whisper-dic removed from login items.")
                else:
                    self._notify("Uninstall Failed", "Not currently installed.")
                self._installed_item.title = f"Installed: {installed}"

            callAfter(_ui)

        threading.Thread(target=_run, daemon=True).start()

    def _version_item(self) -> rumps.MenuItem:
        from . import __version__
        version = __version__
        item = rumps.MenuItem(f"Version: {version}")
        item.set_callback(None)
        return item

    def _check_status(self, _sender: Any) -> None:
        def _run():
            provider = self.config.whisper.provider
            lang = self._app.active_language
            ok = self._app.transcriber_health_check()
            status = "reachable" if ok else "UNREACHABLE"
            self._notify(
                f"Provider: {provider} ({status})",
                f"Language: {lang} | Hotkey: {self.config.hotkey.key.replace('_', ' ')}",
            )
        threading.Thread(target=_run, daemon=True).start()

    def _view_logs(self, _sender: Any) -> None:
        log_path = Path.home() / "Library" / "Logs" / "whisper-dictation.log"
        if not log_path.exists():
            self._notify("No Logs", "No log file found yet.")
            return
        from AppKit import NSWorkspace
        NSWorkspace.sharedWorkspace().openFile_(str(log_path))

    def _on_config_changed(self, new_config: Any) -> None:
        """Called from watcher thread when config.toml changes externally."""
        from .log import log
        log("config-watch", "Config changed externally, reloading...")
        old = self.config
        self.config = new_config

        # Non-UI state updates (safe from any thread)
        if new_config.whisper.provider != old.whisper.provider:
            self._app.replace_transcriber(create_transcriber(new_config.whisper))

        if new_config.whisper.language != old.whisper.language:
            self._app.set_language(new_config.whisper.language)

        if new_config.hotkey.key != old.hotkey.key:
            self._app.listener.set_key(new_config.hotkey.key)

        if new_config.audio_feedback.volume != old.audio_feedback.volume:
            self._app.config.audio_feedback.volume = new_config.audio_feedback.volume

        if new_config.paste.auto_send != old.paste.auto_send:
            self._app.config.paste.auto_send = new_config.paste.auto_send

        if new_config.text_commands.enabled != old.text_commands.enabled:
            self._app.cleaner.text_commands = new_config.text_commands.enabled

        ac_changed = (
            new_config.audio_control.enabled != old.audio_control.enabled
            or new_config.audio_control.mute_local != old.audio_control.mute_local
            or new_config.audio_control.devices != old.audio_control.devices
        )
        if ac_changed:
            from .audio_control import AudioController
            self._app.audio_controller = AudioController(new_config.audio_control)

        if new_config.whisper.failover != old.whisper.failover:
            self._app.config.whisper.failover = new_config.whisper.failover

        rw_changed = (
            new_config.rewrite.enabled != old.rewrite.enabled
            or new_config.rewrite.mode != old.rewrite.mode
            or new_config.rewrite.model != old.rewrite.model
            or new_config.rewrite.prompt != old.rewrite.prompt
        )
        if rw_changed:
            self._app.config.rewrite = new_config.rewrite
            self.config.rewrite = new_config.rewrite
            if new_config.rewrite.enabled:
                self._recreate_rewriter(notify_missing_key=False)
            else:
                if self._app._rewriter is not None:
                    self._app._rewriter.close()
                    self._app._rewriter = None

        if new_config.recording.preview_provider != old.recording.preview_provider:
            self._app.config.recording.preview_provider = new_config.recording.preview_provider
            self.config.recording.preview_provider = new_config.recording.preview_provider
            self._app.reset_preview_transcriber()

        if new_config.recording.streaming_preview != old.recording.streaming_preview:
            self._app.config.recording.streaming_preview = new_config.recording.streaming_preview

        if new_config.recording.preview_interval != old.recording.preview_interval:
            self._app.config.recording.preview_interval = new_config.recording.preview_interval
            self.config.recording.preview_interval = new_config.recording.preview_interval

        # Recording settings
        if new_config.recording.min_duration != old.recording.min_duration:
            self._app.config.recording.min_duration = new_config.recording.min_duration

        if new_config.recording.max_duration != old.recording.max_duration:
            self._app.config.recording.max_duration = new_config.recording.max_duration

        if new_config.recording.sample_rate != old.recording.sample_rate:
            self._app.config.recording.sample_rate = new_config.recording.sample_rate
            self._app.recorder.sample_rate = new_config.recording.sample_rate

        # Whisper settings that require transcriber recreation
        whisper_params_changed = (
            new_config.whisper.timeout_seconds != old.whisper.timeout_seconds
            or new_config.whisper.prompt != old.whisper.prompt
        )
        if whisper_params_changed:
            self._app.replace_transcriber(create_transcriber(new_config.whisper))

        # Language list
        if new_config.whisper.languages != old.whisper.languages:
            self._app.set_languages(
                list(new_config.whisper.languages),
                active_language=new_config.whisper.language,
            )

        overlay_changed = (
            new_config.overlay.reduced_motion != old.overlay.reduced_motion
            or new_config.overlay.high_contrast != old.overlay.high_contrast
            or abs(new_config.overlay.font_scale - old.overlay.font_scale) > 1e-6
        )
        if overlay_changed:
            self._app.config.overlay = new_config.overlay
            self.config.overlay = new_config.overlay

        # Custom commands
        if new_config.custom_commands != old.custom_commands:
            from . import commands
            if new_config.custom_commands:
                commands.register_custom(new_config.custom_commands)

        # UI updates — must dispatch to main thread
        def _sync_ui():
            if new_config.whisper.provider != old.whisper.provider:
                self._provider_menu.title = f"Provider: {new_config.whisper.provider}"
                for item in self._provider_menu.values():
                    item.state = 1 if item.title == new_config.whisper.provider else 0

            if new_config.whisper.language != old.whisper.language:
                display = LANG_NAMES.get(new_config.whisper.language, new_config.whisper.language)
                self._lang_menu.title = f"Language: {display}"
                for item in self._lang_menu.values():
                    lang_code = item.title.split("(")[-1].rstrip(")") if "(" in item.title else ""
                    item.state = 1 if lang_code == new_config.whisper.language else 0

            if new_config.hotkey.key != old.hotkey.key:
                self._hotkey_menu.title = f"Hotkey: {new_config.hotkey.key.replace('_', ' ')}"
                for item in self._hotkey_menu.values():
                    item.state = 1 if getattr(item, "_hotkey_value", None) == new_config.hotkey.key else 0

            if new_config.audio_feedback.volume != old.audio_feedback.volume:
                pct = int(new_config.audio_feedback.volume * 100)
                self._volume_menu.title = f"Volume: {pct}%"
                self._volume_slider.value = pct

            if new_config.paste.auto_send != old.paste.auto_send:
                self._autosend_item.title = f"Auto-Send: {'on' if new_config.paste.auto_send else 'off'}"

            if new_config.text_commands.enabled != old.text_commands.enabled:
                self._textcmds_item.title = f"Text Commands: {'on' if new_config.text_commands.enabled else 'off'}"

            if ac_changed:
                self._audioctrl_item.title = f"Audio Control: {'on' if new_config.audio_control.enabled else 'off'}"

            if new_config.whisper.failover != old.whisper.failover:
                self._failover_item.title = f"Failover: {'on' if new_config.whisper.failover else 'off'}"

            if rw_changed:
                self._update_rewrite_labels()
                for m, item in self._rewrite_mode_items.items():
                    item.state = 1 if m == new_config.rewrite.mode else 0

            if new_config.recording.streaming_preview != old.recording.streaming_preview:
                sp_on = new_config.recording.streaming_preview
                self._preview_item.title = f"Live Preview: {'on' if sp_on else 'off'}"

            if new_config.recording.preview_interval != old.recording.preview_interval:
                self._preview_interval_item.title = f"Preview Interval: {new_config.recording.preview_interval}s"

            if new_config.recording.preview_provider != old.recording.preview_provider:
                label = new_config.recording.preview_provider or new_config.whisper.provider
                self._preview_provider_menu.title = f"Preview Provider: {label}"
                for item in self._preview_provider_menu.values():
                    item.state = 1 if item.title == label else 0

            if new_config.recording.min_duration != old.recording.min_duration:
                self._min_dur_item.title = f"Min Duration: {new_config.recording.min_duration}s"

            if new_config.recording.max_duration != old.recording.max_duration:
                self._max_dur_item.title = f"Max Duration: {new_config.recording.max_duration}s"

            if whisper_params_changed:
                self._timeout_item.title = f"Timeout: {new_config.whisper.timeout_seconds}s"

            if new_config.recording.device != old.recording.device:
                self._app.recorder.device = new_config.recording.device
                label = new_config.recording.device or "System Default"
                self._mic_menu.title = f"Microphone: {label}"
                for item in self._mic_menu.values():
                    item.state = 1 if getattr(item, "_mic_device", object()) == new_config.recording.device else 0

            if overlay_changed:
                rm = new_config.overlay.reduced_motion
                hc = new_config.overlay.high_contrast
                scale = new_config.overlay.font_scale
                self._overlay_reduce_item.title = f"Reduced Motion: {'on' if rm else 'off'}"
                self._overlay_contrast_item.title = f"High Contrast: {'on' if hc else 'off'}"
                self._overlay_scale_menu.title = f"Text Size: {int(scale * 100)}%"
                for value, item in self._overlay_scale_items.items():
                    item.state = 1 if abs(value - scale) < 1e-6 else 0
                self._apply_overlay_accessibility()

            self._notify("Config Reloaded", "Settings updated from config.toml")

        callAfter(_sync_ui)

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
        self._apply_overlay_accessibility()

        # Update transcriber
        self._app.replace_transcriber(create_transcriber(self.config.whisper))

        # Update listener key
        self._app.listener.set_key(self.config.hotkey.key)

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
                self._notify(
                    "Accessibility Permission Required",
                    "Open System Settings > Privacy & Security > Accessibility and add this app.",
                )
        except ImportError:
            pass

    def _start_dictation(self) -> None:
        if _env_flag(_SMOKE_NO_INPUT_ENV):
            callAfter(self._finish_startup)
            return

        self._check_permissions()

        if not self._app.startup_health_checks():
            provider = self.config.whisper.provider
            if provider == "groq" and not self.config.whisper.groq.api_key.strip():
                self._notify("Groq API Key Missing", "Run: whisper-dic set whisper.groq.api_key YOUR_KEY")
            elif provider == "local":
                self._notify("Local Whisper Unreachable", "Start your whisper.cpp server, then restart whisper-dic.")
            else:
                self._notify("Startup Failed", "Whisper provider is unreachable. Run: whisper-dic status")
            return

        # Start listener on main thread — macOS 14+ requires TSM calls from main queue
        callAfter(self._finish_startup)

    def _finish_startup(self) -> None:
        """Main-thread: start listener and timers after health checks pass."""
        if _env_flag(_SMOKE_NO_INPUT_ENV):
            print("[ready] Smoke mode enabled (input hooks disabled).")
            return

        self._app.start_listener()
        self._health_timer.start()
        self._device_timer.start()
        self._config_watcher.start()
        key = self.config.hotkey.key.replace("_", " ")
        self._notify("Ready", f"Hold {key} to dictate. Double-tap to cycle language.")
        print(f"[ready] Hold {key} to dictate. Hold {key} + Ctrl to dictate + send.")


def run_menubar(config_path: Path) -> int:
    from .cli import _check_single_instance, _rotate_log_if_needed
    if not _check_single_instance():
        return 1
    _rotate_log_if_needed()

    # Hide Python from Dock — menu bar only
    from AppKit import NSApplication
    NSApplication.sharedApplication().setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory

    # Ensure config exists — copy template on first run
    first_run = False
    if not config_path.exists():
        import shutil
        from importlib.resources import files
        example = files("whisper_dic").joinpath("config.example.toml")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(example), config_path)
        config_path.chmod(0o600)
        first_run = True

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
