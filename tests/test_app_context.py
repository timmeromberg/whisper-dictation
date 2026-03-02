"""Tests for app_context module."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from whisper_dic.app_context import (
    BROWSER,
    CATEGORIES,
    CHAT,
    CODING,
    EMAIL,
    WRITING,
    category_for_app,
    resolve_context,
)

# --- category_for_app ---


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_terminal(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.apple.Terminal") == CODING


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_cursor(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.todesktop.230313mzl4w4u92") == CODING


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_slack(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.tinyspeck.slackmacgap") == CHAT


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_mail(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.apple.mail") == EMAIL


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_obsidian(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("md.obsidian") == WRITING


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_safari(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.apple.Safari") == BROWSER


@patch("whisper_dic.app_context.sys")
def test_category_for_app_macos_unknown(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("com.example.unknown") is None


@patch("whisper_dic.app_context.sys")
def test_category_for_app_empty_string(mock_sys):
    mock_sys.platform = "darwin"
    assert category_for_app("") is None


@patch("whisper_dic.app_context.sys")
def test_category_for_app_windows_code(mock_sys):
    mock_sys.platform = "win32"
    assert category_for_app("Code.exe") == CODING


@patch("whisper_dic.app_context.sys")
def test_category_for_app_windows_case_insensitive(mock_sys):
    mock_sys.platform = "win32"
    assert category_for_app("OUTLOOK.EXE") == EMAIL
    assert category_for_app("outlook.exe") == EMAIL
    assert category_for_app("Outlook.exe") == EMAIL


@patch("whisper_dic.app_context.sys")
def test_category_for_app_windows_slack(mock_sys):
    mock_sys.platform = "win32"
    assert category_for_app("Slack.exe") == CHAT


@patch("whisper_dic.app_context.sys")
def test_category_for_app_linux_returns_none(mock_sys):
    mock_sys.platform = "linux"
    assert category_for_app("some-app") is None


# --- resolve_context ---


@dataclass
class _MockContextConfig:
    enabled: bool = True
    prompt: str = ""


@patch("whisper_dic.app_context.sys")
def test_resolve_context_known_enabled(mock_sys):
    mock_sys.platform = "darwin"
    configs = {CODING: _MockContextConfig(enabled=True)}
    ctx = resolve_context("com.apple.Terminal", configs)
    assert ctx.category == CODING
    assert ctx.app_id == "com.apple.Terminal"


@patch("whisper_dic.app_context.sys")
def test_resolve_context_known_disabled(mock_sys):
    mock_sys.platform = "darwin"
    configs = {CODING: _MockContextConfig(enabled=False)}
    ctx = resolve_context("com.apple.Terminal", configs)
    assert ctx.category is None  # disabled → falls back to global


@patch("whisper_dic.app_context.sys")
def test_resolve_context_unknown_app(mock_sys):
    mock_sys.platform = "darwin"
    configs = {CODING: _MockContextConfig(enabled=True)}
    ctx = resolve_context("com.example.unknown", configs)
    assert ctx.category is None
    assert ctx.app_id == "com.example.unknown"


@patch("whisper_dic.app_context.sys")
def test_resolve_context_empty_app_id(mock_sys):
    mock_sys.platform = "darwin"
    configs = {CODING: _MockContextConfig(enabled=True)}
    ctx = resolve_context("", configs)
    assert ctx.category is None


@patch("whisper_dic.app_context.sys")
def test_resolve_context_missing_config_for_category(mock_sys):
    mock_sys.platform = "darwin"
    configs = {}  # no configs at all
    ctx = resolve_context("com.apple.Terminal", configs)
    assert ctx.category is None  # no config → falls back


def test_categories_list():
    assert len(CATEGORIES) == 5
    assert CODING in CATEGORIES
    assert CHAT in CATEGORIES
    assert EMAIL in CATEGORIES
    assert WRITING in CATEGORIES
    assert BROWSER in CATEGORIES
