"""Targeted tests for menubar thread-safety helpers."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="menubar is macOS-only")


def _bare_app():
    from whisper_dic.menubar import DictationMenuBar

    app = DictationMenuBar.__new__(DictationMenuBar)
    app._notify = MagicMock()
    app._onboarding_state_path = Path("/tmp/whisper-dic-menubar-test-onboarding.json")
    app._onboarding_state = {"introduced": True, "dismissed": False, "steps": {}}
    return app


def _config_with_context_enabled(enabled: bool):
    from whisper_dic.config import (
        AppConfig,
        AudioFeedbackConfig,
        ContextConfig,
        HotkeyConfig,
        PasteConfig,
        RecordingConfig,
        RewriteConfig,
        TextCommandsConfig,
        WhisperConfig,
    )

    contexts = {
        "coding": ContextConfig(enabled=enabled, prompt=""),
        "chat": ContextConfig(enabled=True, prompt=""),
        "email": ContextConfig(enabled=True, prompt=""),
        "writing": ContextConfig(enabled=True, prompt=""),
        "browser": ContextConfig(enabled=True, prompt=""),
    }

    return AppConfig(
        hotkey=HotkeyConfig(),
        recording=RecordingConfig(),
        paste=PasteConfig(),
        text_commands=TextCommandsConfig(),
        whisper=WhisperConfig(),
        audio_feedback=AudioFeedbackConfig(),
        rewrite=RewriteConfig(enabled=False, mode="light", contexts=contexts),
    )


class TestMenuBarThreadSafety:
    def test_onboarding_state_defaults_when_missing(self, tmp_path: Path) -> None:
        app = _bare_app()
        app._onboarding_state_path = tmp_path / "missing.json"

        state = app._load_onboarding_state()

        assert state["introduced"] is False
        assert state["dismissed"] is False
        assert state["steps"]["permissions"] is False
        assert state["steps"]["provider"] is False
        assert state["steps"]["test_dictation"] is False
        assert state["steps"]["privacy"] is False

    def test_onboarding_state_roundtrip(self, tmp_path: Path) -> None:
        app = _bare_app()
        app._onboarding_state_path = tmp_path / "onboarding.json"
        app._onboarding_state = app._default_onboarding_state()
        app._onboarding_state["introduced"] = True
        app._onboarding_state["steps"]["provider"] = True

        app._save_onboarding_state()

        reloaded = app._load_onboarding_state()
        assert reloaded["introduced"] is True
        assert reloaded["steps"]["provider"] is True

    def test_mark_onboarding_step_updates_state_and_menu(self, tmp_path: Path) -> None:
        app = _bare_app()
        app._onboarding_state_path = tmp_path / "onboarding.json"
        app._onboarding_state = app._default_onboarding_state()
        app._onboarding_menu = SimpleNamespace(title="")
        app._onboarding_step_items = {
            "permissions": SimpleNamespace(state=0),
            "provider": SimpleNamespace(state=0),
            "test_dictation": SimpleNamespace(state=0),
            "privacy": SimpleNamespace(state=0),
        }

        app._mark_onboarding_step("permissions")

        assert app._onboarding_state["steps"]["permissions"] is True
        assert app._onboarding_step_items["permissions"].state == 1
        assert app._onboarding_menu.title == "Getting Started: 1/4"

    def test_mark_onboarding_step_notifies_on_completion(self, tmp_path: Path) -> None:
        app = _bare_app()
        app._onboarding_state_path = tmp_path / "onboarding.json"
        app._onboarding_state = app._default_onboarding_state()
        app._onboarding_state["steps"]["permissions"] = True
        app._onboarding_state["steps"]["provider"] = True
        app._onboarding_state["steps"]["test_dictation"] = True
        app._onboarding_menu = SimpleNamespace(title="")
        app._onboarding_step_items = {
            "permissions": SimpleNamespace(state=1),
            "provider": SimpleNamespace(state=1),
            "test_dictation": SimpleNamespace(state=1),
            "privacy": SimpleNamespace(state=0),
        }

        app._mark_onboarding_step("privacy")

        app._notify.assert_called_once_with(
            "Quick Start Complete",
            "You can reopen this checklist from the menu anytime.",
        )

    def test_sync_context_menu_labels(self) -> None:
        app = _bare_app()
        app._context_items = {
            "coding": SimpleNamespace(state=1),
            "chat": SimpleNamespace(state=0),
        }

        app._sync_context_menu_labels({"coding": SimpleNamespace(enabled=False)})

        assert app._context_items["coding"].state == 0
        assert app._context_items["chat"].state == 1

    def test_notify_dispatches_via_call_after(self) -> None:
        from whisper_dic.menubar import DictationMenuBar, rumps

        app = DictationMenuBar.__new__(DictationMenuBar)
        with patch("whisper_dic.menubar.callAfter") as call_after:
            app._notify("Title", "Message")
        call_after.assert_called_once_with(rumps.notification, "whisper-dic", "Title", "Message")

    def test_on_state_change_dispatches_to_main(self) -> None:
        app = _bare_app()
        with patch("whisper_dic.menubar.callAfter") as call_after:
            app._on_state_change("idle", "")
        call_after.assert_called_once()
        fn, state, detail = call_after.call_args.args
        assert fn == app._on_state_change_main
        assert state == "idle"
        assert detail == ""

    def test_copy_history_entry_handles_empty_text(self) -> None:
        app = _bare_app()
        sender = SimpleNamespace(_history_text="   ")

        app._copy_history_entry(sender)

        app._notify.assert_called_once_with("Copy Failed", "History entry is empty.")

    def test_copy_history_entry_handles_pbcopy_failure(self) -> None:
        app = _bare_app()
        sender = SimpleNamespace(_history_text="example")

        with patch("subprocess.run", side_effect=OSError("pbcopy missing")):
            app._copy_history_entry(sender)

        app._notify.assert_called_once_with("Copy Failed", "Could not copy entry to clipboard.")

    def test_check_provider_health_handles_transcriber_errors(self) -> None:
        app = _bare_app()
        app.config = SimpleNamespace(whisper=SimpleNamespace(provider="local"))
        app._app = SimpleNamespace(transcriber_health_check=MagicMock(side_effect=RuntimeError("boom")))

        app._check_provider_health()

        app._notify.assert_called_once_with(
            "Connection Failed",
            "local provider is unreachable. Check your settings.",
        )

    def test_finish_startup_skips_input_hooks_in_smoke_mode(self) -> None:
        app = _bare_app()
        app._app = SimpleNamespace(start_listener=MagicMock())
        app._health_timer = SimpleNamespace(start=MagicMock())
        app._device_timer = SimpleNamespace(start=MagicMock())
        app._config_watcher = SimpleNamespace(start=MagicMock())

        with patch.dict("os.environ", {"WHISPER_DIC_SMOKE_NO_INPUT": "1"}, clear=False):
            app._finish_startup()

        app._app.start_listener.assert_not_called()
        app._health_timer.start.assert_not_called()
        app._device_timer.start.assert_not_called()
        app._config_watcher.start.assert_not_called()

    def test_finish_startup_starts_hooks_when_not_in_smoke_mode(self) -> None:
        app = _bare_app()
        app._app = SimpleNamespace(start_listener=MagicMock())
        app._health_timer = SimpleNamespace(start=MagicMock())
        app._device_timer = SimpleNamespace(start=MagicMock())
        app._config_watcher = SimpleNamespace(start=MagicMock())
        app.config = SimpleNamespace(hotkey=SimpleNamespace(key="left_option"))

        with patch.dict("os.environ", {"WHISPER_DIC_SMOKE_NO_INPUT": "0"}, clear=False):
            app._finish_startup()

        app._app.start_listener.assert_called_once_with()
        app._health_timer.start.assert_called_once_with()
        app._device_timer.start.assert_called_once_with()
        app._config_watcher.start.assert_called_once_with()

    def test_start_dictation_smoke_mode_skips_health_checks(self) -> None:
        app = _bare_app()
        app._check_permissions = MagicMock()
        app._app = SimpleNamespace(startup_health_checks=MagicMock(return_value=True))

        with (
            patch.dict("os.environ", {"WHISPER_DIC_SMOKE_NO_INPUT": "1"}, clear=False),
            patch("whisper_dic.menubar.callAfter") as call_after,
        ):
            app._start_dictation()

        app._check_permissions.assert_not_called()
        app._app.startup_health_checks.assert_not_called()
        call_after.assert_called_once_with(app._finish_startup)

    def test_config_reload_applies_context_toggle_changes(self) -> None:
        old = _config_with_context_enabled(True)
        new = _config_with_context_enabled(False)

        app = _bare_app()
        app.config = old
        app._app = SimpleNamespace(
            config=deepcopy(old),
            replace_transcriber=MagicMock(),
            set_language=MagicMock(),
            listener=SimpleNamespace(set_key=MagicMock()),
            cleaner=SimpleNamespace(text_commands=True),
            audio_controller=MagicMock(),
            _rewriter=None,
            reset_preview_transcriber=MagicMock(),
            recorder=SimpleNamespace(sample_rate=16000, device=None),
            set_languages=MagicMock(),
        )
        app._rewrite_mode_items = {
            "light": SimpleNamespace(state=0),
            "medium": SimpleNamespace(state=0),
            "full": SimpleNamespace(state=0),
            "custom": SimpleNamespace(state=0),
        }
        app._context_items = {
            "coding": SimpleNamespace(state=1),
            "chat": SimpleNamespace(state=1),
            "email": SimpleNamespace(state=1),
            "writing": SimpleNamespace(state=1),
            "browser": SimpleNamespace(state=1),
        }
        app._update_rewrite_labels = MagicMock()

        with patch("whisper_dic.menubar.callAfter", side_effect=lambda fn, *args: fn(*args)):
            app._on_config_changed(new)

        assert app._app.config.rewrite.contexts["coding"].enabled is False
        assert app._context_items["coding"].state == 0
