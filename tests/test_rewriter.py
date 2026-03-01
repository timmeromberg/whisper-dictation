"""Tests for AI rewriting module."""

from unittest.mock import MagicMock, patch

import pytest

from whisper_dic.rewriter import Rewriter


@pytest.fixture
def rewriter():
    rw = Rewriter(api_key="test-key", model="test-model", prompt="Fix grammar.")
    yield rw
    rw.close()


def test_rewrite_success(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello, how are you?"}}]
    }

    with patch.object(rewriter._client, "post", return_value=mock_response):
        result = rewriter.rewrite("hello how are you")

    assert result == "Hello, how are you?"


def test_rewrite_api_error_returns_original(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch.object(rewriter._client, "post", return_value=mock_response):
        result = rewriter.rewrite("hello world")

    assert result == "hello world"


def test_rewrite_exception_returns_original(rewriter: Rewriter) -> None:
    with patch.object(rewriter._client, "post", side_effect=Exception("connection failed")):
        result = rewriter.rewrite("hello world")

    assert result == "hello world"


def test_rewrite_empty_input(rewriter: Rewriter) -> None:
    result = rewriter.rewrite("")
    assert result == ""

    result = rewriter.rewrite("   ")
    assert result == "   "


def test_rewrite_empty_response_returns_original(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": ""}}]
    }

    with patch.object(rewriter._client, "post", return_value=mock_response):
        result = rewriter.rewrite("hello world")

    assert result == "hello world"


def test_rewrite_sends_correct_payload(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Fixed text."}}]
    }

    with patch.object(rewriter._client, "post", return_value=mock_response) as mock_post:
        rewriter.rewrite("some text")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["model"] == "test-model"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"] == "Fix grammar."
    assert payload["messages"][1]["role"] == "user"
    assert payload["messages"][1]["content"] == "some text"
