"""Tests for AI rewriting module."""

from unittest.mock import MagicMock, patch

import pytest

from whisper_dic.rewriter import CONTEXT_PROMPTS, Rewriter, prompt_for_context


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
    user_content = payload["messages"][1]["content"]
    assert "---TRANSCRIPTION---" in user_content
    assert "some text" in user_content
    assert "---END TRANSCRIPTION---" in user_content


def test_rewrite_with_prompt_override(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Overridden."}}]
    }

    with patch.object(rewriter._client, "post", return_value=mock_response) as mock_post:
        rewriter.rewrite("some text", prompt_override="Custom override prompt.")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["messages"][0]["content"] == "Custom override prompt."


def test_rewrite_without_override_uses_default(rewriter: Rewriter) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Default."}}]
    }

    with patch.object(rewriter._client, "post", return_value=mock_response) as mock_post:
        rewriter.rewrite("some text")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["messages"][0]["content"] == "Fix grammar."


# --- prompt_for_context ---


def test_prompt_for_context_with_custom_prompt() -> None:
    result = prompt_for_context("coding", "My custom coding prompt.", "light", "")
    assert result == "My custom coding prompt."


def test_prompt_for_context_empty_prompt_uses_builtin() -> None:
    result = prompt_for_context("coding", "", "light", "")
    assert result == CONTEXT_PROMPTS["coding"]


def test_prompt_for_context_no_category_uses_global() -> None:
    result = prompt_for_context(None, "", "medium", "")
    assert "Fix grammar" in result


def test_prompt_for_context_unknown_category_uses_global() -> None:
    result = prompt_for_context("nonexistent", "", "light", "custom fallback")
    assert "punctuation" in result.lower()  # light preset


def test_context_prompts_has_all_categories() -> None:
    for cat in ("coding", "chat", "email", "writing", "browser"):
        assert cat in CONTEXT_PROMPTS
        assert len(CONTEXT_PROMPTS[cat]) > 50
