"""Tests for voice commands."""

from __future__ import annotations

import pytest

from commands import _COMMANDS, _parse_shortcut, execute, list_commands, register_custom


@pytest.fixture(autouse=True)
def _restore_commands():
    """Save and restore the command table to prevent test pollution."""
    original = dict(_COMMANDS)
    yield
    _COMMANDS.clear()
    _COMMANDS.update(original)


class TestParseShortcut:
    def test_single_key(self) -> None:
        vk, flags = _parse_shortcut("a")
        assert vk == 0  # 'a' vk code
        assert flags == 0

    def test_cmd_key(self) -> None:
        vk, flags = _parse_shortcut("cmd+z")
        assert vk == 6  # 'z' vk code
        assert flags != 0  # has cmd flag

    def test_multi_modifier(self) -> None:
        vk, flags = _parse_shortcut("cmd+shift+z")
        assert vk == 6  # 'z'
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
        # Mock _post_key to avoid actually posting key events
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
        assert execute("undo") is True

    def test_unknown_returns_false(self, monkeypatch) -> None:
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
        assert execute("fly to the moon") is False

    def test_alias_resolves(self, monkeypatch) -> None:
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
        assert execute("peace") is True  # alias for "paste"

    def test_strips_punctuation(self, monkeypatch) -> None:
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
        assert execute("Undo.") is True

    def test_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
        assert execute("COPY") is True


class TestRegisterCustom:
    def test_registers_valid_command(self, monkeypatch) -> None:
        monkeypatch.setattr("commands._post_key", lambda vk, flags=0: None)
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
