"""Tests for interactive setup menu."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

simple_term_menu = pytest.importorskip("simple_term_menu", reason="simple_term_menu not available on this platform")

from whisper_dic.menu import (  # noqa: E402
    _BOX_WIDTH,
    LANGUAGE_OPTIONS,
    _boxed_title,
    _prompt_for_groq_key,
    _setting_line,
    _show_choice_menu,
    _show_language_picker,
    _show_menu,
    _write_languages,
    run_setup_menu,
)

# ---------------------------------------------------------------------------
# Minimal TOML config used by run_setup_menu tests
# ---------------------------------------------------------------------------
_MINIMAL_TOML = """\
[hotkey]
key = "left_option"

[whisper]
provider = "local"
language = "en"
languages = ["en"]

[whisper.groq]
api_key = ""

[recording]
min_duration = 0.3
sample_rate = 16000

[paste]
auto_send = false

[text_commands]
enabled = true

[audio_feedback]
volume = 0.2
"""


# ── _boxed_title ──────────────────────────────────────────────────────────


class TestBoxedTitle:
    def test_produces_three_lines(self) -> None:
        result = _boxed_title("HELLO")
        lines = result.split("\n")
        # Three content lines + trailing empty from final \n
        assert len(lines) == 4
        assert lines[3] == ""

    def test_top_border(self) -> None:
        result = _boxed_title("X")
        top = result.split("\n")[0]
        assert top == f"\u2554{'\u2550' * _BOX_WIDTH}\u2557"

    def test_bottom_border(self) -> None:
        result = _boxed_title("X")
        bottom = result.split("\n")[2]
        assert bottom == f"\u2560{'\u2550' * _BOX_WIDTH}\u2563"

    def test_title_centered(self) -> None:
        title = "SETTINGS"
        result = _boxed_title(title)
        middle = result.split("\n")[1]
        assert middle.startswith("\u2551")
        assert middle.endswith("\u2551")
        inner = middle[1:-1]
        assert inner == title.center(_BOX_WIDTH)

    def test_width_matches_constant(self) -> None:
        result = _boxed_title("A")
        for line in result.split("\n"):
            if line:
                assert len(line) == _BOX_WIDTH + 2  # +2 for border chars


# ── _setting_line ─────────────────────────────────────────────────────────


class TestSettingLine:
    def test_format(self) -> None:
        result = _setting_line("Provider", "local")
        assert "Provider:" in result
        assert "local" in result
        assert "[change]" in result

    def test_label_padding(self) -> None:
        result = _setting_line("AB", "xy")
        # "AB:" is 3 chars, padded to 10 => 7 spaces after
        assert result.startswith("  AB:")

    def test_exact_format(self) -> None:
        result = _setting_line("Provider", "local")
        expected = f"  {'Provider:':<10} {'local':<14} [change]"
        assert result == expected


# ── _show_menu ────────────────────────────────────────────────────────────


class TestShowMenu:
    @patch("whisper_dic.menu.TerminalMenu")
    @patch("whisper_dic.menu._clear_screen")
    def test_returns_none_when_show_returns_none(
        self, _mock_clear: MagicMock, mock_tm_class: MagicMock
    ) -> None:
        mock_tm_class.return_value.show.return_value = None
        result = _show_menu(["a", "b"], "Title")
        assert result is None

    @patch("whisper_dic.menu.TerminalMenu")
    @patch("whisper_dic.menu._clear_screen")
    def test_returns_int_when_show_returns_index(
        self, _mock_clear: MagicMock, mock_tm_class: MagicMock
    ) -> None:
        mock_tm_class.return_value.show.return_value = 2
        result = _show_menu(["a", "b", "c"], "Title")
        assert result == 2
        assert isinstance(result, int)

    @patch("whisper_dic.menu.TerminalMenu")
    @patch("whisper_dic.menu._clear_screen")
    def test_passes_cursor_index(
        self, _mock_clear: MagicMock, mock_tm_class: MagicMock
    ) -> None:
        mock_tm_class.return_value.show.return_value = 1
        _show_menu(["a", "b"], "Title", cursor_index=1)
        _, kwargs = mock_tm_class.call_args
        assert kwargs["cursor_index"] == 1

    @patch("whisper_dic.menu.TerminalMenu")
    @patch("whisper_dic.menu._clear_screen")
    def test_calls_clear_screen(
        self, mock_clear: MagicMock, mock_tm_class: MagicMock
    ) -> None:
        mock_tm_class.return_value.show.return_value = 0
        _show_menu(["a"], "Title")
        mock_clear.assert_called_once()


# ── _show_choice_menu ─────────────────────────────────────────────────────


class TestShowChoiceMenu:
    @patch("whisper_dic.menu._show_menu")
    def test_marks_current_value_with_bullet(self, mock_show: MagicMock) -> None:
        mock_show.return_value = 1
        _show_choice_menu("Pick", ["alpha", "beta"], "beta")
        entries = mock_show.call_args[0][0]
        assert entries[0].startswith(" ")  # not current
        assert entries[1].startswith("\u25cf")  # bullet for current

    @patch("whisper_dic.menu._show_menu")
    def test_returns_selected_option(self, mock_show: MagicMock) -> None:
        mock_show.return_value = 0
        result = _show_choice_menu("Pick", ["alpha", "beta"], "beta")
        assert result == "alpha"

    @patch("whisper_dic.menu._show_menu")
    def test_returns_none_on_cancel(self, mock_show: MagicMock) -> None:
        mock_show.return_value = None
        result = _show_choice_menu("Pick", ["alpha", "beta"], "alpha")
        assert result is None

    @patch("whisper_dic.menu._show_menu")
    def test_cursor_starts_on_current_value(self, mock_show: MagicMock) -> None:
        mock_show.return_value = None
        _show_choice_menu("Pick", ["alpha", "beta", "gamma"], "gamma")
        kwargs = mock_show.call_args[1]
        assert kwargs["cursor_index"] == 2

    @patch("whisper_dic.menu._show_menu")
    def test_cursor_defaults_to_zero_when_value_missing(self, mock_show: MagicMock) -> None:
        mock_show.return_value = None
        _show_choice_menu("Pick", ["alpha", "beta"], "nonexistent")
        kwargs = mock_show.call_args[1]
        assert kwargs["cursor_index"] == 0


# ── _prompt_for_groq_key ─────────────────────────────────────────────────


class TestPromptForGroqKey:
    @patch("whisper_dic.menu._clear_screen")
    @patch("builtins.input", return_value="gsk_abc123")
    def test_returns_key_on_valid_input(
        self, _mock_input: MagicMock, _mock_clear: MagicMock
    ) -> None:
        result = _prompt_for_groq_key()
        assert result == "gsk_abc123"

    @patch("whisper_dic.menu._clear_screen")
    @patch("builtins.input", return_value="  gsk_spaces  ")
    def test_strips_whitespace(
        self, _mock_input: MagicMock, _mock_clear: MagicMock
    ) -> None:
        result = _prompt_for_groq_key()
        assert result == "gsk_spaces"

    @patch("whisper_dic.menu._clear_screen")
    @patch("builtins.input", return_value="")
    def test_returns_none_on_empty_input(
        self, _mock_input: MagicMock, _mock_clear: MagicMock
    ) -> None:
        result = _prompt_for_groq_key()
        assert result is None

    @patch("whisper_dic.menu._clear_screen")
    @patch("builtins.input", return_value="   ")
    def test_returns_none_on_whitespace_only(
        self, _mock_input: MagicMock, _mock_clear: MagicMock
    ) -> None:
        result = _prompt_for_groq_key()
        assert result is None

    @patch("whisper_dic.menu._clear_screen")
    @patch("builtins.input", side_effect=EOFError)
    def test_returns_none_on_eof(
        self, _mock_input: MagicMock, _mock_clear: MagicMock
    ) -> None:
        result = _prompt_for_groq_key()
        assert result is None


# ── _show_language_picker ─────────────────────────────────────────────────


class TestShowLanguagePicker:
    @patch("whisper_dic.menu._show_menu")
    def test_returns_list_on_done(self, mock_show: MagicMock) -> None:
        # First call: select Done (index = len(LANGUAGE_OPTIONS) + 1)
        mock_show.return_value = len(LANGUAGE_OPTIONS) + 1
        result = _show_language_picker(["en"])
        assert result == ["en"]

    @patch("whisper_dic.menu._show_menu")
    def test_returns_none_on_cancel(self, mock_show: MagicMock) -> None:
        mock_show.return_value = len(LANGUAGE_OPTIONS) + 2
        result = _show_language_picker(["en"])
        assert result is None

    @patch("whisper_dic.menu._show_menu")
    def test_returns_none_when_show_returns_none(self, mock_show: MagicMock) -> None:
        mock_show.return_value = None
        result = _show_language_picker(["en"])
        assert result is None

    @patch("whisper_dic.menu._show_menu")
    def test_toggle_adds_language(self, mock_show: MagicMock) -> None:
        # First call: toggle "nl" (index 2), second call: Done
        mock_show.side_effect = [2, len(LANGUAGE_OPTIONS) + 1]
        result = _show_language_picker(["en"])
        assert result is not None
        assert "en" in result
        assert "nl" in result

    @patch("whisper_dic.menu._show_menu")
    def test_toggle_removes_language_when_multiple(self, mock_show: MagicMock) -> None:
        # Toggle "en" off (index 0) when two are selected, then Done
        mock_show.side_effect = [0, len(LANGUAGE_OPTIONS) + 1]
        result = _show_language_picker(["en", "nl"])
        assert result is not None
        assert "en" not in result
        assert "nl" in result

    @patch("whisper_dic.menu._show_menu")
    def test_prevents_deselecting_last_language(self, mock_show: MagicMock) -> None:
        # Try to toggle off the only selected language, then Done
        mock_show.side_effect = [0, len(LANGUAGE_OPTIONS) + 1]
        result = _show_language_picker(["en"])
        assert result is not None
        assert "en" in result  # still selected because it was the only one

    @patch("whisper_dic.menu._show_menu")
    def test_preserves_language_order(self, mock_show: MagicMock) -> None:
        # Toggle "de" (index 3), then Done => order follows LANGUAGE_OPTIONS
        mock_show.side_effect = [3, len(LANGUAGE_OPTIONS) + 1]
        result = _show_language_picker(["nl"])
        assert result is not None
        # "nl" is at index 2, "de" at index 3 in LANGUAGE_OPTIONS
        assert result.index("nl") < result.index("de")

    @patch("whisper_dic.menu._show_menu")
    def test_done_with_all_deselected_returns_none(self, mock_show: MagicMock) -> None:
        # This shouldn't normally happen since we prevent deselecting last,
        # but if selected set is somehow empty at Done, returns None.
        # We can only get here if started with empty (edge case).
        mock_show.return_value = len(LANGUAGE_OPTIONS) + 1
        result = _show_language_picker([])
        assert result is None


# ── _write_languages ──────────────────────────────────────────────────────


class TestWriteLanguages:
    def test_replaces_existing_languages_line(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[whisper]\nlanguage = "en"\nlanguages = ["en"]\n',
            encoding="utf-8",
        )
        _write_languages(cfg, ["en", "nl", "de"])
        text = cfg.read_text(encoding="utf-8")
        assert 'languages = ["en", "nl", "de"]' in text

    def test_inserts_after_language_when_missing(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[whisper]\nlanguage = "en"\n',
            encoding="utf-8",
        )
        _write_languages(cfg, ["en", "fr"])
        text = cfg.read_text(encoding="utf-8")
        assert 'languages = ["en", "fr"]' in text
        # Should appear after the language line
        lines = text.split("\n")
        lang_idx = next(i for i, line in enumerate(lines) if line.startswith('language = '))
        langs_idx = next(i for i, line in enumerate(lines) if line.startswith('languages = '))
        assert langs_idx == lang_idx + 1

    def test_preserves_other_content(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[whisper]\nprovider = "local"\nlanguage = "en"\nlanguages = ["en"]\n'
            "\n[hotkey]\nkey = \"left_option\"\n",
            encoding="utf-8",
        )
        _write_languages(cfg, ["ja"])
        text = cfg.read_text(encoding="utf-8")
        assert 'provider = "local"' in text
        assert 'key = "left_option"' in text
        assert 'languages = ["ja"]' in text

    def test_single_language(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[whisper]\nlanguages = ["en", "nl"]\n',
            encoding="utf-8",
        )
        _write_languages(cfg, ["ko"])
        text = cfg.read_text(encoding="utf-8")
        assert 'languages = ["ko"]' in text


# ── run_setup_menu ────────────────────────────────────────────────────────


def _make_config(tmp_path: Path) -> Path:
    """Write minimal TOML config and return its path."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(_MINIMAL_TOML, encoding="utf-8")
    return cfg


class TestRunSetupMenuQuitAndStart:
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_quit_on_escape(
        self, mock_resolve: MagicMock, mock_show: MagicMock, tmp_path: Path
    ) -> None:
        from whisper_dic.config import load_config

        mock_resolve.return_value = (load_config, MagicMock())
        mock_show.return_value = None  # escape pressed
        result = run_setup_menu(_make_config(tmp_path))
        assert result == "quit"

    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_quit_on_selection_9(
        self, mock_resolve: MagicMock, mock_show: MagicMock, tmp_path: Path
    ) -> None:
        from whisper_dic.config import load_config

        mock_resolve.return_value = (load_config, MagicMock())
        mock_show.return_value = 9  # Quit entry
        result = run_setup_menu(_make_config(tmp_path))
        assert result == "quit"

    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_start_on_selection_8(
        self, mock_resolve: MagicMock, mock_show: MagicMock, tmp_path: Path
    ) -> None:
        from whisper_dic.config import load_config

        mock_resolve.return_value = (load_config, MagicMock())
        mock_show.return_value = 8  # Start Dictating
        result = run_setup_menu(_make_config(tmp_path))
        assert result == "start"


class TestRunSetupMenuProvider:
    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_changes_provider(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # First loop: select provider (0), second loop: quit (9)
        mock_show.side_effect = [0, 9]
        mock_choice.return_value = "groq"

        cfg = _make_config(tmp_path)
        # Provide a groq key so the prompt isn't triggered
        cfg.write_text(
            cfg.read_text().replace('api_key = ""', 'api_key = "gsk_test"'),
            encoding="utf-8",
        )
        run_setup_menu(cfg)
        mock_set.assert_any_call(cfg, "whisper.provider", "groq")

    @patch("whisper_dic.menu._prompt_for_groq_key")
    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_prompts_for_groq_key_when_switching_to_groq_without_key(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        mock_prompt: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select provider (0), then quit (9)
        mock_show.side_effect = [0, 9]
        mock_choice.return_value = "groq"
        mock_prompt.return_value = "gsk_new_key"

        run_setup_menu(_make_config(tmp_path))
        mock_prompt.assert_called_once()
        mock_set.assert_any_call(tmp_path / "config.toml", "whisper.groq.api_key", "gsk_new_key")

    @patch("whisper_dic.menu._prompt_for_groq_key")
    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_cancels_groq_switch_when_key_prompt_returns_none(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        mock_prompt: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select provider (0), then quit (9)
        mock_show.side_effect = [0, 9]
        mock_choice.return_value = "groq"
        mock_prompt.return_value = None  # user cancelled key prompt

        run_setup_menu(_make_config(tmp_path))
        # Provider should NOT have been set
        provider_calls = [c for c in mock_set.call_args_list if c[0][1] == "whisper.provider"]
        assert len(provider_calls) == 0

    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_no_change_when_same_provider_selected(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        mock_show.side_effect = [0, 9]
        mock_choice.return_value = "local"  # same as current

        run_setup_menu(_make_config(tmp_path))
        assert not mock_set.called


class TestRunSetupMenuHotkey:
    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_changes_hotkey(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select hotkey (2), then quit (9)
        mock_show.side_effect = [2, 9]
        mock_choice.return_value = "right_option"

        run_setup_menu(_make_config(tmp_path))
        mock_set.assert_called_once_with(
            tmp_path / "config.toml", "hotkey.key", "right_option"
        )


class TestRunSetupMenuVolume:
    @patch("whisper_dic.menu._show_choice_menu")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_changes_volume(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_choice: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select volume (3), then quit (9)
        mock_show.side_effect = [3, 9]
        mock_choice.return_value = "50%"

        run_setup_menu(_make_config(tmp_path))
        mock_set.assert_called_once_with(
            tmp_path / "config.toml", "audio_feedback.volume", "0.5"
        )


class TestRunSetupMenuToggles:
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_toggles_auto_send(
        self, mock_resolve: MagicMock, mock_show: MagicMock, tmp_path: Path
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select auto_send (4), then quit (9)
        mock_show.side_effect = [4, 9]

        run_setup_menu(_make_config(tmp_path))
        mock_set.assert_called_once_with(
            tmp_path / "config.toml", "paste.auto_send", "true"
        )

    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_toggles_text_commands(
        self, mock_resolve: MagicMock, mock_show: MagicMock, tmp_path: Path
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select text_commands (5), then quit (9)
        mock_show.side_effect = [5, 9]

        run_setup_menu(_make_config(tmp_path))
        mock_set.assert_called_once_with(
            tmp_path / "config.toml", "text_commands.enabled", "false"
        )


class TestRunSetupMenuGroqKey:
    @patch("whisper_dic.menu._prompt_for_groq_key")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_sets_groq_api_key(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_prompt: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select groq key (6), then quit (9)
        mock_show.side_effect = [6, 9]
        mock_prompt.return_value = "gsk_my_key"

        run_setup_menu(_make_config(tmp_path))
        mock_set.assert_called_once_with(
            tmp_path / "config.toml", "whisper.groq.api_key", "gsk_my_key"
        )

    @patch("whisper_dic.menu._prompt_for_groq_key")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_groq_key_prompt_cancelled(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_prompt: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select groq key (6), then quit (9)
        mock_show.side_effect = [6, 9]
        mock_prompt.return_value = None

        run_setup_menu(_make_config(tmp_path))
        assert not mock_set.called


class TestRunSetupMenuLanguages:
    @patch("whisper_dic.menu._write_languages")
    @patch("whisper_dic.menu._show_language_picker")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_changes_languages(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_picker: MagicMock,
        mock_write: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        # Select languages (1), then quit (9)
        mock_show.side_effect = [1, 9]
        mock_picker.return_value = ["en", "nl"]

        cfg = _make_config(tmp_path)
        run_setup_menu(cfg)
        mock_write.assert_called_once_with(cfg, ["en", "nl"])
        mock_set.assert_called_once_with(cfg, "whisper.language", "en")

    @patch("whisper_dic.menu._write_languages")
    @patch("whisper_dic.menu._show_language_picker")
    @patch("whisper_dic.menu._show_menu")
    @patch("whisper_dic.menu._resolve_dictation_functions")
    def test_language_picker_cancelled(
        self,
        mock_resolve: MagicMock,
        mock_show: MagicMock,
        mock_picker: MagicMock,
        mock_write: MagicMock,
        tmp_path: Path,
    ) -> None:
        from whisper_dic.config import load_config

        mock_set = MagicMock()
        mock_resolve.return_value = (load_config, mock_set)
        mock_show.side_effect = [1, 9]
        mock_picker.return_value = None

        run_setup_menu(_make_config(tmp_path))
        mock_write.assert_not_called()
        assert not mock_set.called
