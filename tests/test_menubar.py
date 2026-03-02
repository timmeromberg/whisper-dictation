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
