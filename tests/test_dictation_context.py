"""Tests for per-app rewrite context behavior in DictationApp pipeline."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from whisper_dic.app_context import RewriteContext
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
from whisper_dic.dictation import DictationApp
from whisper_dic.recorder import RecordingResult
from whisper_dic.rewriter import prompt_for_mode


def _config_for_context(coding_enabled: bool, coding_prompt: str = "") -> AppConfig:
    contexts = {
        "coding": ContextConfig(enabled=coding_enabled, prompt=coding_prompt),
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
        audio_feedback=AudioFeedbackConfig(enabled=False),
        rewrite=RewriteConfig(enabled=False, mode="light", contexts=contexts),
    )


def test_pipeline_uses_context_prompt_and_forwards_app_id() -> None:
    config = _config_for_context(coding_enabled=True, coding_prompt="Use coding style prompt.")
    listener = SimpleNamespace(start=MagicMock(), stop=MagicMock(), set_key=MagicMock())
    transcriber = MagicMock()
    transcriber.language = "en"
    transcriber.transcribe.return_value = "raw transcript"
    transcriber.health_check.return_value = True

    with (
        patch("whisper_dic.recorder.sd"),
        patch("whisper_dic.dictation.HotkeyListener", return_value=listener),
        patch("whisper_dic.dictation.create_transcriber", return_value=transcriber),
        patch("whisper_dic.dictation.frontmost_app_id", return_value="frontmost-app"),
        patch(
            "whisper_dic.dictation.resolve_context",
            return_value=RewriteContext(category="coding", app_id="frontmost-app"),
        ),
    ):
        app = DictationApp(config)
        app.cleaner.clean = MagicMock(return_value="cleaned transcript")
        app._rewriter = MagicMock()
        app._rewriter.rewrite.return_value = "rewritten transcript"
        app.paster = MagicMock()
        app.history = MagicMock()

        result = RecordingResult(audio_bytes=b"audio", duration_seconds=1.0, sample_count=16000)
        app._run_pipeline(result)

        app._rewriter.rewrite.assert_called_once()
        assert app._rewriter.rewrite.call_args.kwargs["prompt_override"] == "Use coding style prompt."
        app.paster.paste.assert_called_once_with(
            "rewritten transcript",
            auto_send=False,
            app_id="frontmost-app",
        )
        app.stop()


def test_pipeline_falls_back_to_global_prompt_when_context_disabled() -> None:
    config = _config_for_context(coding_enabled=False, coding_prompt="")
    listener = SimpleNamespace(start=MagicMock(), stop=MagicMock(), set_key=MagicMock())
    transcriber = MagicMock()
    transcriber.language = "en"
    transcriber.transcribe.return_value = "raw transcript"
    transcriber.health_check.return_value = True

    with (
        patch("whisper_dic.recorder.sd"),
        patch("whisper_dic.dictation.HotkeyListener", return_value=listener),
        patch("whisper_dic.dictation.create_transcriber", return_value=transcriber),
        patch("whisper_dic.dictation.frontmost_app_id", return_value="frontmost-app"),
        patch(
            "whisper_dic.dictation.resolve_context",
            return_value=RewriteContext(category=None, app_id="frontmost-app"),
        ),
    ):
        app = DictationApp(config)
        app.cleaner.clean = MagicMock(return_value="cleaned transcript")
        app._rewriter = MagicMock()
        app._rewriter.rewrite.return_value = "rewritten transcript"
        app.paster = MagicMock()
        app.history = MagicMock()

        result = RecordingResult(audio_bytes=b"audio", duration_seconds=1.0, sample_count=16000)
        app._run_pipeline(result)

        app._rewriter.rewrite.assert_called_once()
        assert app._rewriter.rewrite.call_args.kwargs["prompt_override"] == prompt_for_mode("light", "")
        app.stop()
