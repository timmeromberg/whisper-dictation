"""Interactive setup menu for whisper-dic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from simple_term_menu import TerminalMenu

PROVIDER_OPTIONS = ["local", "groq"]
LANGUAGE_OPTIONS = ["en", "auto", "nl", "de", "fr", "es", "ja", "zh", "ko", "pt", "it", "ru"]
HOTKEY_OPTIONS = ["left_option", "right_option", "left_command", "right_command", "left_shift", "right_shift"]
VOLUME_OPTIONS = ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9", "1.0"]

_BOX_WIDTH = 34
_SEPARATOR = "  " + ("─" * 32)


def _clear_screen() -> None:
    print("\033[2J\033[H", end="")


def _boxed_title(title: str) -> str:
    return (
        f"╔{'═' * _BOX_WIDTH}╗\n"
        f"║{title.center(_BOX_WIDTH)}║\n"
        f"╠{'═' * _BOX_WIDTH}╣\n"
    )


def _setting_line(label: str, value: str) -> str:
    return f"  {(label + ':'):<10} {value:<14} [change]"


def _resolve_dictation_functions() -> tuple[Callable[[Path], Any], Callable[[Path, str, str], None]]:
    from config import load_config, set_config_value
    return load_config, set_config_value


def _show_menu(entries: list[str], title: str, cursor_index: int = 0) -> int | None:
    _clear_screen()
    menu = TerminalMenu(
        entries,
        title=title,
        cursor_index=cursor_index,
        menu_cursor="▶ ",
        menu_cursor_style=("fg_cyan", "bold"),
        menu_highlight_style=("fg_green", "bold"),
        clear_screen=False,
        clear_menu_on_exit=False,
        cycle_cursor=True,
        show_shortcut_hints=False,
    )
    result = menu.show()
    return int(result) if result is not None else None


def _show_choice_menu(menu_title: str, options: list[str], current_value: str) -> str | None:
    entries = [f"{'●' if option == current_value else ' '} {option}" for option in options]
    selected_index = options.index(current_value) if current_value in options else 0
    title = _boxed_title(menu_title) + "\n"
    selection = _show_menu(entries, title, cursor_index=selected_index)
    if selection is None:
        return None
    return options[selection]


def _prompt_for_groq_key() -> str | None:
    _clear_screen()
    print(_boxed_title("GROQ API KEY"))
    print()
    print("  Enter API key and press Enter.")
    print("  Leave blank to cancel.")
    print()
    try:
        value = input("  Groq API Key: ").strip()
    except EOFError:
        return None
    return value if value else None


def _show_language_picker(current_languages: list[str]) -> list[str] | None:
    """Multi-select language picker. Returns new language list or None if cancelled."""
    selected = set(current_languages)

    while True:
        entries = []
        for lang in LANGUAGE_OPTIONS:
            marker = "✓" if lang in selected else " "
            entries.append(f"  [{marker}] {lang}")
        entries.append(_SEPARATOR)
        entries.append("  ✔ Done")
        entries.append("  ✕ Cancel")

        title = _boxed_title("SELECT LANGUAGES") + "  Toggle with Enter. At least one required.\n\n"
        sel = _show_menu(entries, title)

        if sel is None or sel == len(LANGUAGE_OPTIONS) + 2:
            return None

        if sel == len(LANGUAGE_OPTIONS) + 1:
            # Done
            result = [lang for lang in LANGUAGE_OPTIONS if lang in selected]
            return result if result else None

        if sel < len(LANGUAGE_OPTIONS):
            lang = LANGUAGE_OPTIONS[sel]
            if lang in selected:
                if len(selected) > 1:
                    selected.remove(lang)
            else:
                selected.add(lang)


def _write_languages(config_path: Path, languages: list[str]) -> None:
    """Write the languages list directly to config.toml."""
    text = config_path.read_text(encoding="utf-8")
    import re
    # Replace existing languages line
    lang_toml = "[" + ", ".join(f'"{lang}"' for lang in languages) + "]"
    pattern = re.compile(r"(?m)^(\s*languages\s*=\s*).*$")
    if pattern.search(text):
        text = pattern.sub(rf"\g<1>{lang_toml}", text)
    else:
        # Insert after language = line
        text = re.sub(
            r"(?m)^(language\s*=\s*.*)$",
            rf"\1\nlanguages = {lang_toml}",
            text,
            count=1,
        )
    config_path.write_text(text, encoding="utf-8")


def run_setup_menu(config_path: Path) -> str:
    """Run interactive settings menu. Returns 'start' or 'quit'."""
    load_config, set_config_value = _resolve_dictation_functions()

    while True:
        config = load_config(config_path)
        groq_status = "set" if config.whisper.groq.api_key.strip() else "not set"

        langs_display = ", ".join(config.whisper.languages)

        vol_pct = f"{int(config.audio_feedback.volume * 100)}%"

        auto_send_display = "on" if config.paste.auto_send else "off"
        text_cmds_display = "on" if config.text_commands.enabled else "off"

        title = _boxed_title("WHISPER-DIC SETTINGS") + "\n"
        entries = [
            _setting_line("Provider", config.whisper.provider),
            _setting_line("Languages", langs_display),
            _setting_line("Hotkey", config.hotkey.key),
            _setting_line("Volume", vol_pct),
            _setting_line("Auto Send", auto_send_display),
            _setting_line("Text Cmds", text_cmds_display),
            _setting_line("Groq Key", groq_status),
            _SEPARATOR,
            "  ▶ Start Dictating",
            "  ✕ Quit",
        ]

        selection = _show_menu(entries, title)
        if selection is None or selection == 9:
            _clear_screen()
            return "quit"

        if selection == 0:
            provider = _show_choice_menu("SELECT PROVIDER", PROVIDER_OPTIONS, config.whisper.provider)
            if provider is None or provider == config.whisper.provider:
                continue

            if provider == "groq" and not config.whisper.groq.api_key.strip():
                api_key = _prompt_for_groq_key()
                if not api_key:
                    continue
                set_config_value(config_path, "whisper.groq.api_key", api_key)

            set_config_value(config_path, "whisper.provider", provider)
            continue

        if selection == 1:
            new_langs = _show_language_picker(config.whisper.languages)
            if new_langs is not None and new_langs != config.whisper.languages:
                _write_languages(config_path, new_langs)
                # Set active language to first in list
                set_config_value(config_path, "whisper.language", new_langs[0])
            continue

        if selection == 2:
            hotkey = _show_choice_menu("SELECT HOTKEY", HOTKEY_OPTIONS, config.hotkey.key)
            if hotkey is not None and hotkey != config.hotkey.key:
                set_config_value(config_path, "hotkey.key", hotkey)
            continue

        if selection == 3:
            vol_labels = [f"{int(float(v) * 100)}%" for v in VOLUME_OPTIONS]
            current_label = f"{int(config.audio_feedback.volume * 100)}%"
            idx = _show_choice_menu("SET VOLUME", vol_labels, current_label)
            if idx is not None and idx != current_label:
                vol_val = VOLUME_OPTIONS[vol_labels.index(idx)]
                set_config_value(config_path, "audio_feedback.volume", vol_val)
            continue

        if selection == 4:
            new_val = "false" if config.paste.auto_send else "true"
            set_config_value(config_path, "paste.auto_send", new_val)
            continue

        if selection == 5:
            new_val = "false" if config.text_commands.enabled else "true"
            set_config_value(config_path, "text_commands.enabled", new_val)
            continue

        if selection == 6:
            api_key = _prompt_for_groq_key()
            if api_key is not None:
                set_config_value(config_path, "whisper.groq.api_key", api_key)
            continue

        if selection == 8:
            _clear_screen()
            return "start"

