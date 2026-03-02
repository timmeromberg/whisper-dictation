# Commands

## CLI Commands

All commands support `--config PATH` to use a custom config file instead of the default location.

Example:

```bash
whisper-dic --config /path/to/config.toml status
whisper-dic --config /path/to/config.toml set whisper.provider groq
```

### Command reference

| Command | Description |
|---|---|
| `whisper-dic run` | Start in foreground mode (all platforms) |
| `whisper-dic menubar` | Start with menu bar UI (macOS only) |
| `whisper-dic setup` | Interactive setup wizard (macOS only) |
| `whisper-dic setup-local` | Install whisper.cpp server and model for local transcription |
| `whisper-dic doctor` | Run diagnostics (config, provider, mic, permissions, local install) |
| `whisper-dic status` | Show active config and endpoint reachability |
| `whisper-dic provider [groq|local]` | Show or switch provider |
| `whisper-dic set KEY VALUE` | Set one config value |
| `whisper-dic devices` | List available microphones |
| `whisper-dic logs` | Show logs (`-n 200` for tail, `-n f` to follow on macOS/Linux) |
| `whisper-dic discover` | Discover network audio devices |
| `whisper-dic install` | Install login item / auto-start service (macOS only) |
| `whisper-dic uninstall` | Remove login item / auto-start service (macOS only) |
| `whisper-dic version` | Print version |

### Notes

- `setup` is currently macOS-only. On Windows/Linux, use `whisper-dic set KEY VALUE`.
- `menubar` is macOS-only. Use `run` on Windows/Linux.
- On macOS with Python 3.14, `run`/`menubar`/`setup` are blocked by default due to runtime instability.

## Dictation Hotkeys

| Hold | macOS | Windows/Linux | Behavior |
|---|---|---|---|
| Dictate | Left Option | Left Alt | Transcribe and paste |
| Dictate + send | Option + Ctrl | Alt + Ctrl | Paste and press Return |
| Voice command mode | Option + Shift | Alt + Shift | Execute command instead of pasting text |
| Cycle language | Double-tap Option | Double-tap Alt | Switch to next configured language |
| Cancel current recording | Escape (while holding hotkey) | Escape (while holding hotkey) | Cancel and discard recording |

## Built-in Voice Commands

Use voice command mode (hotkey + Shift), then say one of the following:

| Say | macOS | Windows/Linux |
|---|---|---|
| copy / copy that | Cmd+C | Ctrl+C |
| cut / cut that | Cmd+X | Ctrl+X |
| paste / paste that | Cmd+V | Ctrl+V |
| select all | Cmd+A | Ctrl+A |
| undo / undo that | Cmd+Z | Ctrl+Z |
| redo | Cmd+Shift+Z | Ctrl+Shift+Z |
| save / save file | Cmd+S | Ctrl+S |
| find | Cmd+F | Ctrl+F |
| delete / backspace | Delete | Delete |
| enter / return | Return | Return |
| tab | Tab | Tab |
| escape | Escape | Escape |
| close tab | Cmd+W | Ctrl+W |
| new tab | Cmd+T | Ctrl+T |
| new window | Cmd+N | Ctrl+N |
| bold | Cmd+B | Ctrl+B |
| screenshot | Cmd+Ctrl+Shift+4 | macOS only |
| full screenshot | Cmd+Ctrl+Shift+3 | macOS only |

Common Whisper mishearings are auto-mapped (for example `coffee` -> `copy`, `peace` -> `paste`).

## Text Commands

When `text_commands.enabled = true`, spoken punctuation/formatting is converted:

| Say | Inserts |
|---|---|
| period / full stop | `.` |
| comma | `,` |
| question mark | `?` |
| exclamation mark / exclamation point | `!` |
| new line / newline | newline |
| new paragraph | blank line |
| open quote / close quote | curly quotes |
| open paren / close paren | `(` / `)` |
| colon / semicolon | `:` / `;` |
| dash / em dash | em dash |
| hyphen | `-` |
| tab | tab character |

## Custom Voice Commands

Add your own phrase -> shortcut mappings in `[custom_commands]`:

```toml
[custom_commands]
"zoom in" = "cmd+="
"next tab" = "ctrl+tab"
```

See [configuration.md](configuration.md) for full syntax and supported modifiers.
