"""Targeted tests for menubar thread-safety helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="menubar is macOS-only")


def _bare_app():
    from whisper_dic.menubar import DictationMenuBar

    app = DictationMenuBar.__new__(DictationMenuBar)
    app._notify = MagicMock()
    return app


class TestMenuBarThreadSafety:
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
