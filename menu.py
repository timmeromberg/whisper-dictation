"""Interactive setup menu for whisper-dic."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from simple_term_menu import TerminalMenu


PROVIDER_OPTIONS = ["local", "groq"]
LANGUAGE_OPTIONS = ["en", "auto", "nl", "de", "fr", "es", "ja", "zh", "ko", "pt", "it", "ru"]
HOTKEY_OPTIONS = ["left_option", "right_option", "left_command", "right_command", "left_shift", "right_shift"]

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
    # When dictation.py is started as a script, it is loaded as __main__.
    main_module = sys.modules.get("__main__")
    if (
        main_module is not None
        and hasattr(main_module, "load_config")
        and hasattr(main_module, "set_config_value")
    ):
        load_config = getattr(main_module, "load_config")
        set_config_value = getattr(main_module, "set_config_value")
        return load_config, set_config_value

    dictation_module = importlib.import_module("dictation")
    return dictation_module.load_config, dictation_module.set_config_value


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
    return menu.show()


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


def run_setup_menu(config_path: Path) -> str:
    """Run interactive settings menu. Returns 'start' or 'quit'."""
    load_config, set_config_value = _resolve_dictation_functions()

    while True:
        config = load_config(config_path)
        groq_status = "set" if config.whisper.groq.api_key.strip() else "not set"

        title = _boxed_title("WHISPER-DIC SETTINGS") + "\n"
        entries = [
            _setting_line("Provider", config.whisper.provider),
            _setting_line("Language", config.whisper.language),
            _setting_line("Hotkey", config.hotkey.key),
            _setting_line("Groq Key", groq_status),
            _SEPARATOR,
            "  ▶ Start Dictating",
            "  ✕ Quit",
        ]

        selection = _show_menu(entries, title)
        if selection is None or selection == 6:
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
            language = _show_choice_menu("SELECT LANGUAGE", LANGUAGE_OPTIONS, config.whisper.language)
            if language is not None and language != config.whisper.language:
                set_config_value(config_path, "whisper.language", language)
            continue

        if selection == 2:
            hotkey = _show_choice_menu("SELECT HOTKEY", HOTKEY_OPTIONS, config.hotkey.key)
            if hotkey is not None and hotkey != config.hotkey.key:
                set_config_value(config_path, "hotkey.key", hotkey)
            continue

        if selection == 3:
            api_key = _prompt_for_groq_key()
            if api_key is not None:
                set_config_value(config_path, "whisper.groq.api_key", api_key)
            continue

        if selection == 5:
            _clear_screen()
            return "start"

