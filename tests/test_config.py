"""Tests for config loading and helpers."""

from __future__ import annotations

from pathlib import Path

from dictation import AppConfig, _section, _to_toml_literal, load_config


class TestLoadConfig:
    def test_example_config(self, example_config: Path) -> None:
        config = load_config(example_config)
        assert isinstance(config, AppConfig)
        assert config.hotkey.key == "left_option"
        assert config.whisper.provider == "local"
        assert config.whisper.language == "en"
        assert config.recording.min_duration == 0.3
        assert config.recording.sample_rate == 16000

    def test_minimal_config(self, tmp_config: Path) -> None:
        config = load_config(tmp_config)
        assert config.hotkey.key == "left_option"
        # Defaults should apply
        assert config.whisper.provider == "local"
        assert config.recording.min_duration == 0.3

    def test_empty_config(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.toml"
        p.write_text("")
        config = load_config(p)
        # All defaults
        assert config.hotkey.key == "right_option"
        assert config.whisper.provider == "local"

    def test_custom_values(self, tmp_path: Path) -> None:
        p = tmp_path / "custom.toml"
        p.write_text(
            '[whisper]\nprovider = "groq"\nlanguage = "nl"\n'
            "[recording]\nmin_duration = 0.5\n"
        )
        config = load_config(p)
        assert config.whisper.provider == "groq"
        assert config.whisper.language == "nl"
        assert config.recording.min_duration == 0.5

    def test_invalid_provider_defaults_to_local(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.toml"
        p.write_text('[whisper]\nprovider = "azure"\n')
        config = load_config(p)
        assert config.whisper.provider == "local"

    def test_languages_list(self, tmp_path: Path) -> None:
        p = tmp_path / "langs.toml"
        p.write_text('[whisper]\nlanguages = ["en", "nl", "de"]\n')
        config = load_config(p)
        assert config.whisper.languages == ["en", "nl", "de"]

    def test_language_inserted_into_languages(self, tmp_path: Path) -> None:
        p = tmp_path / "lang.toml"
        p.write_text('[whisper]\nlanguage = "fr"\nlanguages = ["en", "nl"]\n')
        config = load_config(p)
        assert "fr" in config.whisper.languages

    def test_custom_commands(self, tmp_path: Path) -> None:
        p = tmp_path / "cmds.toml"
        p.write_text('[custom_commands]\n"zoom in" = "cmd+="\n')
        config = load_config(p)
        assert config.custom_commands == {"zoom in": "cmd+="}


class TestSection:
    def test_simple(self) -> None:
        data = {"hotkey": {"key": "left_option"}}
        assert _section(data, "hotkey") == {"key": "left_option"}

    def test_nested(self) -> None:
        data = {"whisper": {"local": {"url": "http://localhost:2022"}}}
        assert _section(data, "whisper.local") == {"url": "http://localhost:2022"}

    def test_missing_returns_empty(self) -> None:
        assert _section({}, "nonexistent") == {}

    def test_non_dict_returns_empty(self) -> None:
        data = {"key": "value"}
        assert _section(data, "key") == {}


class TestToTomlLiteral:
    def test_empty_string(self) -> None:
        assert _to_toml_literal("") == '""'

    def test_already_quoted(self) -> None:
        assert _to_toml_literal('"hello"') == '"hello"'

    def test_boolean_true(self) -> None:
        assert _to_toml_literal("true") == "true"

    def test_boolean_false(self) -> None:
        assert _to_toml_literal("False") == "false"

    def test_integer(self) -> None:
        assert _to_toml_literal("42") == "42"

    def test_float(self) -> None:
        assert _to_toml_literal("3.14") == "3.14"

    def test_plain_string_gets_quoted(self) -> None:
        assert _to_toml_literal("hello") == '"hello"'

    def test_escapes_quotes(self) -> None:
        assert _to_toml_literal('say "hi"') == '"say \\"hi\\""'
