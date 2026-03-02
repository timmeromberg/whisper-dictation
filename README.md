# whisper-dic

[![CI](https://github.com/timmeromberg/whisper-dic/actions/workflows/ci.yml/badge.svg)](https://github.com/timmeromberg/whisper-dic/actions/workflows/ci.yml)
[![E2E](https://github.com/timmeromberg/whisper-dic/actions/workflows/e2e.yml/badge.svg)](https://github.com/timmeromberg/whisper-dic/actions/workflows/e2e.yml)
[![PyPI](https://img.shields.io/pypi/v/whisper-dic)](https://pypi.org/project/whisper-dic/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/timmeromberg/whisper-dic/blob/main/LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

System-wide hold-to-dictate for macOS, Windows, and Linux. Hold a key, speak, release - your words appear wherever the cursor is.

## Features

- **Hold-to-dictate** - hold a hotkey to record, release to transcribe and paste
- **Voice commands** - hold Option/Alt + Shift, say "copy", "paste", "undo", "screenshot", etc.
- **Custom voice commands** - map any spoken phrase to a keyboard shortcut via `[custom_commands]`
- **Auto-send** - hold Option/Alt + Ctrl to auto-press Return after pasting (for chat/terminal)
- **Multi-language** - double-tap the hotkey to cycle between configured languages
- **Text commands** - say "period", "new line", "question mark" for punctuation
- **AI rewriting** - optional LLM-powered cleanup of transcriptions (grammar, punctuation, capitalization)
- **Per-app context** - automatically adapts rewrite style based on the frontmost app (coding, chat, email, writing, browser)
- **Filler removal** - automatically strips "um", "uh", "you know", etc.
- **Live preview** - see transcription text appearing in real-time while you speak (opt-in)
- **Provider failover** - automatically tries the other provider when the primary fails
- **Whisper prompt** - bias transcription toward domain-specific vocabulary
- **Persistent history** - transcription history saved across sessions
- **Actionable errors** - error notifications tell you what to fix, not just what failed
- **Microphone selection** - choose which input device to use, switch live from menu bar
- **Auto-mute** - mute Mac speakers, Android devices, Chromecasts during recording (macOS)
- **Menu bar app** - shows recording status and mic level, switch settings without restart (macOS)
- **Auto-start** - install as login item with automatic crash recovery (macOS)
- **Config validation** - invalid values are clamped to sane defaults with warnings

## Quick Start

### 1. Prerequisites

- **macOS** 10.13+, **Windows** 10+, or **Linux**
- Python 3.12+
- **macOS runtime note:** Python 3.12/3.13 is recommended for stability. Python 3.14 is blocked for `run`/`menubar`/`setup` by default because it may crash on some systems.
- A Whisper provider: [Groq API key](https://console.groq.com/) (free tier available) **or** a local [whisper.cpp](https://github.com/ggml-org/whisper.cpp) server

### 2. Install

**Option A - pipx (recommended):**

```bash
# macOS - includes menu bar support
pipx install "whisper-dic[macos]"

# Windows/Linux
pipx install whisper-dic
```

Do not have pipx? Install it with `pip install --user pipx && pipx ensurepath`.

**Option B - pip:**

```bash
pip install "whisper-dic[macos]"    # macOS
pip install whisper-dic              # Windows/Linux
```

**Option C - from source:**

```bash
git clone https://github.com/timmeromberg/whisper-dic.git
cd whisper-dic
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[macos]"          # Windows/Linux: pip install -e .
```

### Updating

```bash
# pipx
pipx upgrade whisper-dic

# pip
pip install --upgrade whisper-dic

# from source
git pull && pip install -e ".[macos]"   # Windows/Linux: pip install -e .
```

### Uninstalling

```bash
# pipx
pipx uninstall whisper-dic

# pip
pip uninstall whisper-dic
```

Optional cleanup:

- Remove config and history:
  - macOS/Linux: `~/.config/whisper-dic/`
  - Windows: `%APPDATA%/whisper-dic/`
- Remove local whisper.cpp assets created by `setup-local`:
  - macOS/Linux: `~/.local/share/whisper-dic/`
  - Windows: `%LOCALAPPDATA%/whisper-dic/`

### 3. Configure

On first run, whisper-dic creates a config file at `~/.config/whisper-dic/config.toml` (macOS/Linux) or `%APPDATA%/whisper-dic/config.toml` (Windows).

Edit it to set your provider:

```toml
[whisper]
provider = "groq"           # or "local"

[whisper.groq]
api_key = "gsk_..."         # get from console.groq.com
```

Or use the interactive setup (macOS only):

```bash
whisper-dic setup
```

### 4. Permissions

**macOS:** Grant these in **System Settings > Privacy & Security**:

| Permission | Why | What to add |
|---|---|---|
| **Microphone** | Audio recording | Your terminal app (for example iTerm or Terminal) |
| **Accessibility** | Global hotkey + paste simulation | Your terminal app **and** the Python binary whisper-dic runs with |

To find which Python binary to add:

```bash
python3 -c "import sys; print(sys.executable)"
```

**Windows/Linux:** No special platform permissions are required for basic operation.

### 5. Run

```bash
# Menu bar mode (recommended, macOS only)
whisper-dic menubar

# Foreground mode (all platforms)
whisper-dic run
```

### 6. Test It

Hold **Left Option** (macOS) or **Left Alt** (Windows/Linux), speak, release.

## Usage

### Hotkey Modifiers

| Hold | macOS | Windows/Linux | Behavior |
|---|---|---|---|
| Dictate | **Left Option** | **Left Alt** | Transcribe and paste |
| Dictate + send | **Option + Ctrl** | **Alt + Ctrl** | Paste and press Return |
| Voice command | **Option + Shift** | **Alt + Shift** | Execute a shortcut instead of pasting text |
| Cycle language | **Double-tap Option** | **Double-tap Alt** | Switch to next configured language |
| Cancel recording | **Escape (while holding hotkey)** | **Escape (while holding hotkey)** | Cancel and discard current recording |

`Option/Alt + Ctrl` is per-dictation auto-send. `paste.auto_send = true` applies auto-send globally.

## Documentation

Full documentation is in [`docs/`](docs/):

- **[Configuration](docs/configuration.md)** - all settings with examples
- **[Commands](docs/commands.md)** - CLI, voice commands, text commands, custom commands
- **[Local Setup](docs/local-setup.md)** - whisper.cpp installation and models
- **[Menu Bar](docs/menubar.md)** - macOS menu bar features and accessibility
- **[Privacy](docs/privacy.md)** - data handling and provider data flows
- **[Troubleshooting](docs/troubleshooting.md)** - common issues and fixes
- **[Development](docs/development.md)** - contributing, tests, project structure

## License

MIT
