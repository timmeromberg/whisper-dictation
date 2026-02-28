# whisper-dic

System-wide hold-to-dictate for macOS. Hold a key, speak, release — your words appear wherever the cursor is. Uses Whisper for transcription via local server or Groq cloud API.

## Features

- **Hold-to-dictate** — hold a hotkey to record, release to transcribe and paste
- **Voice commands** — hold Option + Shift, say "copy", "paste", "undo", "screenshot", etc.
- **Custom voice commands** — map any spoken phrase to a keyboard shortcut via `[custom_commands]`
- **Auto-send** — hold Option + Ctrl to auto-press Return after pasting (for chat/terminal)
- **Multi-language** — double-tap the hotkey to cycle between configured languages
- **Text commands** — say "period", "new line", "question mark" for punctuation
- **Filler removal** — automatically strips "um", "uh", "you know", etc.
- **Provider failover** — automatically tries the other provider when the primary fails
- **Whisper prompt** — bias transcription toward domain-specific vocabulary
- **Persistent history** — transcription history saved across sessions
- **Actionable errors** — error notifications tell you what to fix, not just what failed
- **Auto-mute** — mute Mac speakers, Android devices, Chromecasts during recording
- **Menu bar app** — shows recording status and mic level, switch settings without restart
- **Auto-start** — install as login item with automatic crash recovery
- **Config validation** — invalid values are clamped to sane defaults with warnings

## Quick Start

### 1. Prerequisites

- macOS 10.13+
- Python 3.10+
- A Whisper provider: [Groq API key](https://console.groq.com/) (free tier available) **or** a local [whisper.cpp](https://github.com/ggerganov/whisper.cpp) server

### 2. Install

```bash
git clone https://github.com/timmeromberg/whisper-dictation.git
cd whisper-dictation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Alternative: editable install
.venv/bin/pip install -e .
```

### 3. Configure

```bash
cp config.example.toml config.toml
```

Edit `config.toml`:

```toml
[whisper]
provider = "groq"           # or "local"

[whisper.groq]
api_key = "gsk_your_key"    # get from console.groq.com
```

Or use the interactive setup:

```bash
./whisper-dic setup
```

### 4. Grant macOS Permissions

Before first use, grant these in **System Settings > Privacy & Security**:

| Permission | Why | What to add |
|---|---|---|
| **Microphone** | Audio recording | Your Terminal app (e.g. iTerm, Terminal) |
| **Accessibility** | Global hotkey + paste simulation | Your Terminal app **and** `.venv/bin/python` |

If permissions are missing, whisper-dic will show a notification telling you which one to fix.

### 5. Run

```bash
# Menu bar mode (recommended)
./whisper-dic menubar

# Or foreground mode (for debugging)
./whisper-dic run
```

### 6. Test

Hold **Left Option**, speak, release. Your words should appear at the cursor.

## Usage

### Hotkey Modifiers

| Hold | Behavior |
|------|----------|
| **Option** | Dictate — transcribe and paste |
| **Option + Ctrl** | Dictate + send — paste and press Return |
| **Option + Shift** | Voice command — execute instead of paste |
| **Double-tap Option** | Cycle language |

### Voice Commands

Hold Option + Shift and say any of these:

| Say | Does |
|-----|------|
| copy / copy that | Cmd+C |
| cut / cut that | Cmd+X |
| paste / paste that | Cmd+V |
| select all | Cmd+A |
| undo / undo that | Cmd+Z |
| redo | Cmd+Shift+Z |
| save / save file | Cmd+S |
| find | Cmd+F |
| delete / backspace | Delete |
| enter / return | Return |
| tab | Tab |
| escape | Escape |
| close tab | Cmd+W |
| new tab | Cmd+T |
| new window | Cmd+N |
| bold | Cmd+B |
| screenshot | Cmd+Ctrl+Shift+4 (area select) |
| full screenshot | Cmd+Ctrl+Shift+3 |

Common Whisper mishearings are handled automatically ("peace" -> "paste", "coffee" -> "copy", etc.).

### Text Commands

When enabled, spoken punctuation is converted automatically:

| Say | Inserts |
|-----|---------|
| period / full stop | . |
| comma | , |
| question mark | ? |
| exclamation mark | ! |
| new line | newline |
| new paragraph | blank line |
| open quote / close quote | curly quotes |
| colon / semicolon | : / ; |
| dash / em dash | — |

## CLI Commands

```bash
whisper-dic run              # Start in foreground
whisper-dic menubar          # Start with menu bar icon
whisper-dic setup            # Interactive setup wizard
whisper-dic status           # Show config and endpoint health
whisper-dic provider [groq|local]  # Show or switch provider
whisper-dic set KEY VALUE    # Update a config value (run 'whisper-dic set -h' for examples)
whisper-dic logs             # Show recent log entries (use -n f to follow)
whisper-dic discover         # Find audio devices on your network
whisper-dic install          # Install as login item (auto-start)
whisper-dic uninstall        # Remove login item
whisper-dic version          # Show version
```

## Configuration

All settings are in `config.toml`. See `config.example.toml` for the full reference.

### Whisper Provider

**Groq (cloud)** — fast, no GPU needed, free tier available:
```toml
[whisper]
provider = "groq"

[whisper.groq]
api_key = "gsk_..."
```

**Local (whisper.cpp)** — fully offline, requires running server:
```toml
[whisper]
provider = "local"

[whisper.local]
url = "http://localhost:2022/v1/audio/transcriptions"
model = "large-v3"
```

### Failover

Automatically try the other provider when the primary fails:

```toml
[whisper]
failover = true
```

### Whisper Prompt

Bias transcription toward specific vocabulary (technical terms, names, etc.):

```toml
[whisper]
prompt = "whisper-dic, macOS, Groq, PyAudio"
```

### Languages

```toml
[whisper]
language = "en"
languages = ["en", "nl", "de"]  # double-tap cycles through these
```

### Audio Feedback

```toml
[audio_feedback]
enabled = true
start_frequency = 880    # beep when recording starts
stop_frequency = 660     # beep when recording stops
duration_seconds = 0.08
volume = 0.2             # 0.0 - 1.0
```

### Auto-Mute Devices

Mute speakers and connected devices while recording:

```toml
[audio_control]
enabled = true
mute_local = true   # mute Mac speakers
```

Add network devices (run `whisper-dic discover` to find them):

```toml
[[audio_control.devices]]
type = "adb"
name = "Android Tablet"

[[audio_control.devices]]
type = "chromecast"
name = "Living Room Speaker"

[[audio_control.devices]]
type = "custom"
name = "My Device"
mute_command = "some-command --mute"
unmute_command = "some-command --unmute"
```

### Custom Voice Commands

Map any spoken phrase to a keyboard shortcut:

```toml
[custom_commands]
"zoom in" = "cmd+="
"zoom out" = "cmd+-"
"next tab" = "ctrl+tab"
"close window" = "cmd+w"
```

Use with Option + Shift (voice command mode).

## Auto-Start at Login

```bash
# Install (creates launchd plist, starts at login, auto-restarts on crash)
./whisper-dic install

# View logs
tail -f ~/Library/Logs/whisper-dictation.log

# Uninstall
./whisper-dic uninstall
```

## Menu Bar

When running in menubar mode, the status bar icon shows:

| Icon | State |
|------|-------|
| 🎤 | Idle — ready to dictate |
| 🔴 + level bar | Recording — shows mic input level |
| ⏳ | Transcribing — sending audio to Whisper |

Click the icon to switch language, provider, hotkey, beep volume, or quit.

## Troubleshooting

**Hotkey not working?**
- Grant Accessibility permission in System Settings
- Check the hotkey isn't used by another app

**Transcription failing?**
- Run `whisper-dic status` to check endpoint health
- Check logs: `tail -f ~/Library/Logs/whisper-dictation.log`
- For Groq: verify API key is set and valid

**Text not appearing?**
- Grant Accessibility permission (needed for Cmd+V simulation)
- Make sure cursor is in a text field

**No start beep?**
- Check `audio_feedback.enabled = true` in config
- Increase `audio_feedback.volume`

**Long dictations failing intermittently?**
- Audio is compressed as FLAC before upload to minimize network errors
- Transient SSL errors are retried automatically (up to 3 times)
- If persistent, check your network connection

## Project Structure

```
whisper-dictation/
├── whisper-dic              # entry point (bash wrapper)
├── cli.py                   # CLI commands, argparse, main()
├── config.py                # config loading, validation, live-reload
├── dictation.py             # core hold-to-dictate engine
├── menubar.py               # menu bar UI
├── recorder.py              # microphone capture
├── transcriber.py           # Whisper API clients
├── hotkey.py                # global hotkey listener
├── commands.py              # voice command table
├── cleaner.py               # text cleanup
├── paster.py                # clipboard + paste
├── history.py               # persistent transcription history
├── overlay.py               # floating status overlay
├── audio_control.py         # device muting
├── log.py                   # logging
├── menu.py                  # setup TUI
├── tests/                   # pytest test suite
├── pyproject.toml           # project config (ruff, pytest)
├── config.example.toml      # config template
├── config.toml              # your config (gitignored)
└── requirements.txt         # dependencies
```

## License

MIT
