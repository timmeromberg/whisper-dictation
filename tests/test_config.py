"""Tests for config loading and helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from whisper_dic.config import (
    AppConfig,
    _section,
    _to_toml_literal,
    load_config,
    set_config_section,
    set_config_value,
)


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
        assert config.hotkey.key == "left_option"
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


class TestValidation:
    def test_negative_min_duration_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "neg.toml"
        p.write_text("[recording]\nmin_duration = -1.0\n")
        config = load_config(p)
        assert config.recording.min_duration == 0.1

    def test_max_less_than_min_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "maxmin.toml"
        p.write_text("[recording]\nmin_duration = 0.5\nmax_duration = 0.1\n")
        config = load_config(p)
        assert config.recording.max_duration == 300.0

    def test_invalid_sample_rate_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "sr.toml"
        p.write_text("[recording]\nsample_rate = 12345\n")
        config = load_config(p)
        assert config.recording.sample_rate == 16000

    def test_volume_over_1_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "vol.toml"
        p.write_text("[audio_feedback]\nvolume = 5.0\n")
        config = load_config(p)
        assert config.audio_feedback.volume == 1.0

    def test_volume_negative_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "volneg.toml"
        p.write_text("[audio_feedback]\nvolume = -0.5\n")
        config = load_config(p)
        assert config.audio_feedback.volume == 0.0

    def test_empty_language_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "lang.toml"
        p.write_text('[whisper]\nlanguage = ""\n')
        config = load_config(p)
        assert config.whisper.language == "en"

    def test_negative_timeout_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "timeout.toml"
        p.write_text("[whisper]\ntimeout_seconds = -10\n")
        config = load_config(p)
        assert config.whisper.timeout_seconds == 120.0

    def test_overlay_font_scale_over_limit_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "overlay.toml"
        p.write_text("[overlay]\nfont_scale = 5.0\n")
        config = load_config(p)
        assert config.overlay.font_scale == 2.0

    def test_overlay_font_scale_below_limit_clamped(self, tmp_path: Path) -> None:
        p = tmp_path / "overlay.toml"
        p.write_text("[overlay]\nfont_scale = 0.1\n")
        config = load_config(p)
        assert config.overlay.font_scale == 0.75


class TestSetConfigValue:
    def test_set_config_value_preserves_existing_file_on_replace_error(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[whisper]\nprovider = "local"\n', encoding="utf-8")

        with patch("whisper_dic.config.os.replace", side_effect=RuntimeError("replace failed")):
            with pytest.raises(RuntimeError):
                set_config_value(config_path, "whisper.provider", "groq")

        # Original file remains intact when atomic replace fails.
        assert 'provider = "local"' in config_path.read_text(encoding="utf-8")
        assert not list(tmp_path.glob(".config.toml.*.tmp"))

    @pytest.mark.skipif(os.name == "nt", reason="POSIX chmod semantics")
    def test_set_config_value_preserves_mode_bits(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text('[whisper]\nprovider = "local"\n', encoding="utf-8")
        config_path.chmod(0o640)

        set_config_value(config_path, "whisper.provider", "groq")

        mode = config_path.stat().st_mode & 0o777
        assert mode == 0o640


class TestContextConfig:
    def test_empty_config_gets_all_default_contexts(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.toml"
        p.write_text("")
        config = load_config(p)
        assert len(config.rewrite.contexts) == 5
        for cat in ("coding", "chat", "email", "writing", "browser"):
            assert cat in config.rewrite.contexts
            assert config.rewrite.contexts[cat].enabled is True
            assert config.rewrite.contexts[cat].prompt == ""

    def test_partial_contexts_in_config(self, tmp_path: Path) -> None:
        p = tmp_path / "partial.toml"
        p.write_text(
            "[rewrite.contexts.coding]\n"
            "enabled = false\n"
            '\nprompt = "Custom coding prompt."\n'
        )
        config = load_config(p)
        assert config.rewrite.contexts["coding"].enabled is False
        assert config.rewrite.contexts["coding"].prompt == "Custom coding prompt."
        # Other categories still get defaults
        assert config.rewrite.contexts["chat"].enabled is True
        assert config.rewrite.contexts["chat"].prompt == ""

    def test_context_disabled(self, tmp_path: Path) -> None:
        p = tmp_path / "disabled.toml"
        p.write_text("[rewrite.contexts.email]\nenabled = false\n")
        config = load_config(p)
        assert config.rewrite.contexts["email"].enabled is False

    def test_context_with_custom_prompt(self, tmp_path: Path) -> None:
        p = tmp_path / "prompt.toml"
        p.write_text('[rewrite.contexts.chat]\nprompt = "Be very casual."\n')
        config = load_config(p)
        assert config.rewrite.contexts["chat"].prompt == "Be very casual."


class TestSnippetsConfig:
    def test_empty_config_has_no_snippets(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.toml"
        p.write_text("")
        config = load_config(p)
        assert config.snippets == {}

    def test_loads_snippets(self, tmp_path: Path) -> None:
        p = tmp_path / "snippets.toml"
        p.write_text(
            '[snippets]\n'
            '"my email" = "tim@example.com"\n'
            '"my address" = "123 Main St"\n'
        )
        config = load_config(p)
        assert config.snippets == {
            "my email": "tim@example.com",
            "my address": "123 Main St",
        }

    def test_multiline_snippet(self, tmp_path: Path) -> None:
        p = tmp_path / "multi.toml"
        p.write_text(
            '[snippets]\n'
            '"signature" = """Best regards,\nTim"""\n'
        )
        config = load_config(p)
        assert config.snippets["signature"] == "Best regards,\nTim"


class TestSetConfigSection:
    def test_creates_new_section(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text('[whisper]\nprovider = "local"\n')
        set_config_section(p, "snippets", {"my email": "tim@example.com"})
        config = load_config(p)
        assert config.snippets == {"my email": "tim@example.com"}

    def test_replaces_existing_section(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text(
            '[snippets]\n"old" = "old value"\n'
            '\n[whisper]\nprovider = "local"\n'
        )
        set_config_section(p, "snippets", {"new": "new value"})
        config = load_config(p)
        assert config.snippets == {"new": "new value"}
        assert config.whisper.provider == "local"

    def test_empty_data_clears_section(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text('[snippets]\n"old" = "old value"\n')
        set_config_section(p, "snippets", {})
        config = load_config(p)
        assert config.snippets == {}

    def test_preserves_other_sections(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text(
            '[hotkey]\nkey = "left_option"\n'
            '\n[snippets]\n"old" = "old value"\n'
            '\n[whisper]\nprovider = "groq"\n'
        )
        set_config_section(p, "snippets", {"email": "a@b.com"})
        config = load_config(p)
        assert config.hotkey.key == "left_option"
        assert config.whisper.provider == "groq"
        assert config.snippets == {"email": "a@b.com"}
