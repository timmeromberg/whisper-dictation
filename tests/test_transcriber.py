"""Tests for Whisper transcription clients."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from whisper_dic.transcriber import (
    GroqWhisperTranscriber,
    LocalWhisperTranscriber,
    _describe_http_error,
    create_transcriber,
    create_transcriber_for,
)

LOCAL_URL = "http://localhost:2022/v1/audio/transcriptions"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
FAKE_URL = "http://localhost:9999/v1/audio/transcriptions"


class TestDescribeHttpError:
    def test_401(self) -> None:
        resp = MagicMock(status_code=401)
        assert "invalid or expired" in _describe_http_error(resp)

    def test_403(self) -> None:
        resp = MagicMock(status_code=403)
        assert "permission" in _describe_http_error(resp).lower()

    def test_413(self) -> None:
        resp = MagicMock(status_code=413)
        assert "too large" in _describe_http_error(resp).lower()

    def test_429(self) -> None:
        resp = MagicMock(status_code=429)
        assert "rate limit" in _describe_http_error(resp).lower()

    def test_500(self) -> None:
        resp = MagicMock(status_code=500)
        assert "server error" in _describe_http_error(resp).lower()

    def test_generic(self) -> None:
        resp = MagicMock(status_code=418, text="I'm a teapot")
        result = _describe_http_error(resp)
        assert "418" in result


class TestCreateTranscriber:
    def test_local_default(self) -> None:
        config = SimpleNamespace(
            provider="local", language="en", timeout_seconds=120.0, prompt="",
            local=SimpleNamespace(url=LOCAL_URL, model="large-v3"),
            groq=SimpleNamespace(api_key="", url=GROQ_URL, model="whisper-large-v3"),
        )
        t = create_transcriber(config)
        assert isinstance(t, LocalWhisperTranscriber)
        t.close()

    def test_groq(self) -> None:
        config = SimpleNamespace(
            provider="groq", language="en", timeout_seconds=120.0, prompt="",
            local=SimpleNamespace(url=LOCAL_URL, model="large-v3"),
            groq=SimpleNamespace(api_key="test-key", url=GROQ_URL, model="whisper-large-v3"),
        )
        t = create_transcriber(config)
        assert isinstance(t, GroqWhisperTranscriber)
        t.close()

    def test_unsupported_provider(self) -> None:
        config = SimpleNamespace(
            provider="azure", language="en", timeout_seconds=120.0,
            prompt="", local=None, groq=None,
        )
        with pytest.raises(ValueError, match="Unsupported"):
            create_transcriber(config)

    def test_no_local_config_uses_defaults(self) -> None:
        config = SimpleNamespace(
            provider="local", language="en", timeout_seconds=60.0,
            prompt="", local=None, groq=None,
        )
        t = create_transcriber(config)
        assert isinstance(t, LocalWhisperTranscriber)
        t.close()


class TestCreateTranscriberFor:
    def test_local_explicit(self) -> None:
        custom_url = "http://custom:1234/v1/audio/transcriptions"
        config = SimpleNamespace(
            provider="groq", language="nl", timeout_seconds=30.0, prompt="test",
            local=SimpleNamespace(url=custom_url, model="base"),
            groq=SimpleNamespace(api_key="key", url=GROQ_URL, model="whisper-large-v3"),
        )
        t = create_transcriber_for(config, "local")
        assert isinstance(t, LocalWhisperTranscriber)
        t.close()

    def test_unsupported_raises(self) -> None:
        config = SimpleNamespace(
            language="en", timeout_seconds=120.0,
            prompt="", local=None, groq=None,
        )
        with pytest.raises(ValueError):
            create_transcriber_for(config, "azure")


class TestHealthCheck:
    def test_bad_url(self) -> None:
        t = LocalWhisperTranscriber(url="not-a-url", language="en")
        assert t.health_check() is False
        t.close()

    def test_unreachable(self) -> None:
        unreachable = "http://127.0.0.1:59999/v1/audio/transcriptions"
        t = LocalWhisperTranscriber(url=unreachable, language="en", timeout_seconds=1.0)
        assert t.health_check() is False
        t.close()


class TestTranscribe:
    def test_success(self) -> None:
        t = LocalWhisperTranscriber(url=FAKE_URL, language="en", timeout_seconds=1.0)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"text": " Hello world "}
        with patch.object(t._client, "post", return_value=mock_resp):
            result = t.transcribe(b"fake-audio")
        assert result == "Hello world"
        t.close()

    def test_error_raises(self) -> None:
        t = LocalWhisperTranscriber(url=FAKE_URL, language="en", timeout_seconds=1.0)
        mock_resp = MagicMock(status_code=401)
        with patch.object(t._client, "post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="invalid or expired"):
                t.transcribe(b"fake-audio")
        t.close()

    def test_auto_language_excluded(self) -> None:
        t = LocalWhisperTranscriber(url=FAKE_URL, language="auto", timeout_seconds=1.0)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"text": "ok"}
        with patch.object(t._client, "post", return_value=mock_resp) as mock_post:
            t.transcribe(b"fake-audio")
            call_kwargs = mock_post.call_args
            data = call_kwargs.kwargs.get("data", {})
            assert "language" not in data
        t.close()

    def test_prompt_included(self) -> None:
        t = LocalWhisperTranscriber(
            url=FAKE_URL, language="en", timeout_seconds=1.0,
            prompt="whisper-dic macOS",
        )
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"text": "ok"}
        with patch.object(t._client, "post", return_value=mock_resp) as mock_post:
            t.transcribe(b"fake-audio")
            data = mock_post.call_args.kwargs.get("data", {})
            assert data.get("prompt") == "whisper-dic macOS"
        t.close()
