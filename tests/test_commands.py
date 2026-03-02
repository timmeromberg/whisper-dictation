"""Tests for voice commands and text snippets."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import whisper_dic.commands as commands_mod
from whisper_dic.commands import (
    _COMMANDS,
    _SNIPPETS,
    _parse_shortcut,
    execute,
    init_paster,
    list_commands,
    list_snippets,
    register_custom,
    register_snippets,
)
from whisper_dic.compat import VK_MAP


@pytest.fixture(autouse=True)
def _restore_commands():
    """Save and restore the command and snippet tables to prevent test pollution."""
    original_commands = dict(_COMMANDS)
    original_snippets = dict(_SNIPPETS)
    original_paster = commands_mod._paster
    yield
    _COMMANDS.clear()
    _COMMANDS.update(original_commands)
    _SNIPPETS.clear()
    _SNIPPETS.update(original_snippets)
    commands_mod._paster = original_paster


class TestParseShortcut:
    def test_single_key(self) -> None:
        vk, flags = _parse_shortcut("a")
        assert vk == VK_MAP["a"]
        assert flags == 0

    def test_cmd_key(self) -> None:
        vk, flags = _parse_shortcut("cmd+z")
        assert vk == VK_MAP["z"]
        assert flags != 0  # has cmd flag

    def test_multi_modifier(self) -> None:
        vk, flags = _parse_shortcut("cmd+shift+z")
        assert vk == VK_MAP["z"]
        assert flags != 0

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown key"):
            _parse_shortcut("cmd+nonexistent")

    def test_unknown_modifier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown modifier"):
            _parse_shortcut("superkey+a")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            _parse_shortcut("")


class TestExecute:
    def test_known_command_returns_true(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        assert execute("undo") is True

    def test_unknown_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        assert execute("fly to the moon") is False

    def test_alias_resolves(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        assert execute("peace") is True  # alias for "paste"

    def test_strips_punctuation(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        assert execute("Undo.") is True

    def test_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        assert execute("COPY") is True


class TestRegisterCustom:
    def test_registers_valid_command(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        register_custom({"zoom in": "cmd+="})
        assert execute("zoom in") is True

    def test_invalid_shortcut_skipped(self) -> None:
        # Should log but not crash
        register_custom({"bad cmd": "cmd+nonexistent"})
        assert "bad cmd" not in _COMMANDS


class TestListCommands:
    def test_returns_sorted(self) -> None:
        result = list_commands()
        assert result == sorted(result)
        assert len(result) > 0


class TestCommandTable:
    """Validate the command table is internally consistent."""

    def test_all_vk_codes_are_valid(self) -> None:
        """Every command's VK code must exist in VK_MAP values."""
        valid_vks = set(VK_MAP.values())
        for name, (vk, flags) in _COMMANDS.items():
            assert vk in valid_vks, f"Command '{name}' has unknown VK code {vk}"

    def test_new_tab_uses_t_key(self) -> None:
        """Regression: new tab must use 't' key, not 'tab' key."""
        vk, _ = _COMMANDS["new tab"]
        assert vk == VK_MAP["t"], f"new tab should use 't' ({VK_MAP['t']}), not {vk}"

    def test_close_tab_uses_w_key(self) -> None:
        vk, _ = _COMMANDS["close tab"]
        assert vk == VK_MAP["w"]

    def test_expected_commands_present(self) -> None:
        expected = {
            "copy", "paste", "cut", "undo", "redo",
            "select all", "save", "find", "delete", "backspace",
            "enter", "return", "tab", "escape",
            "new tab", "close tab", "new window", "bold",
            "screenshot", "full screenshot",
        }
        for cmd in expected:
            assert cmd in _COMMANDS, f"Expected command '{cmd}' missing from table"


class TestRegisterSnippets:
    def test_registers_snippets(self) -> None:
        register_snippets({"my email": "tim@example.com"})
        assert _SNIPPETS["my email"] == "tim@example.com"

    def test_normalizes_phrase(self) -> None:
        register_snippets({"  My Email  ": "tim@example.com"})
        assert "my email" in _SNIPPETS

    def test_clears_previous(self) -> None:
        register_snippets({"first": "aaa"})
        register_snippets({"second": "bbb"})
        assert "first" not in _SNIPPETS
        assert "second" in _SNIPPETS

    def test_skips_empty_phrase(self) -> None:
        register_snippets({"": "some text", "  ": "more text"})
        assert len(_SNIPPETS) == 0

    def test_skips_empty_text(self) -> None:
        register_snippets({"trigger": ""})
        assert len(_SNIPPETS) == 0

    def test_warns_on_command_collision(self) -> None:
        # "copy" is a built-in command — snippet should still register but logs warning
        register_snippets({"copy": "some text"})
        assert "copy" in _SNIPPETS

    def test_multiple_snippets(self) -> None:
        register_snippets({
            "my email": "tim@example.com",
            "my address": "123 Main St",
            "signature": "Best,\nTim",
        })
        assert len(_SNIPPETS) == 3


class TestListSnippets:
    def test_returns_copy(self) -> None:
        register_snippets({"greeting": "hello world"})
        result = list_snippets()
        assert result == {"greeting": "hello world"}
        # Mutating returned dict should not affect internal state
        result["new"] = "value"
        assert "new" not in _SNIPPETS

    def test_empty_when_none_registered(self) -> None:
        assert list_snippets() == {}


class TestSnippetExecution:
    def test_snippet_pastes_text(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"my email": "tim@example.com"})

        assert execute("my email") is True
        mock_paster.paste.assert_called_once_with("tim@example.com")

    def test_command_takes_priority_over_snippet(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"copy": "some text"})

        assert execute("copy") is True
        mock_paster.paste.assert_not_called()

    def test_snippet_no_paster_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        commands_mod._paster = None
        register_snippets({"my email": "tim@example.com"})

        assert execute("my email") is False

    def test_snippet_strips_punctuation(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"my email": "tim@example.com"})

        assert execute("My email.") is True
        mock_paster.paste.assert_called_once_with("tim@example.com")

    def test_snippet_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"my email": "tim@example.com"})

        assert execute("MY EMAIL") is True

    def test_no_match_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"my email": "tim@example.com"})

        assert execute("unknown phrase") is False
        mock_paster.paste.assert_not_called()

    def test_snippet_whisper_capitalized_with_period(self, monkeypatch) -> None:
        """Whisper returns 'Session Review.' for snippet 'session review'."""
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"session review": "/session-review"})

        assert execute("Session Review.") is True
        mock_paster.paste.assert_called_once_with("/session-review")

    def test_snippet_registered_with_punctuation(self, monkeypatch) -> None:
        """Snippet trigger registered with punctuation still matches clean input."""
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"My Email!": "tim@example.com"})

        assert execute("my email") is True
        mock_paster.paste.assert_called_once_with("tim@example.com")

    def test_multiline_snippet(self, monkeypatch) -> None:
        monkeypatch.setattr("whisper_dic.commands._post_key", lambda vk, flags=0: None)
        mock_paster = MagicMock()
        init_paster(mock_paster)
        register_snippets({"signature": "Best regards,\nTim"})

        assert execute("signature") is True
        mock_paster.paste.assert_called_once_with("Best regards,\nTim")
