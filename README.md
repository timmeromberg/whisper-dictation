# whisper-dic

System-wide hold-to-dictate for macOS and Windows. Hold a key, speak, release — your words appear wherever the cursor is. Uses Whisper for transcription via local server or Groq cloud API.

## Features

- **Hold-to-dictate** — hold a hotkey to record, release to transcribe and paste
- **Voice commands** — hold Option/Alt + Shift, say "copy", "paste", "undo", "screenshot", etc.
- **Custom voice commands** — map any spoken phrase to a keyboard shortcut via `[custom_commands]`
- **Auto-send** — hold Option/Alt + Ctrl to auto-press Return after pasting (for chat/terminal)
- **Multi-language** — double-tap the hotkey to cycle between configured languages
- **Text commands** — say "period", "new line", "question mark" for punctuation
- **AI rewriting** — optional LLM-powered cleanup of transcriptions (grammar, punctuation, capitalization)
- **Filler removal** — automatically strips "um", "uh", "you know", etc.
- **Live preview** — see transcription text appearing in real-time while you speak (opt-in)
- **Provider failover** — automatically tries the other provider when the primary fails
- **Whisper prompt** — bias transcription toward domain-specific vocabulary
- **Persistent history** — transcription history saved across sessions
- **Actionable errors** — error notifications tell you what to fix, not just what failed
- **Microphone selection** — choose which input device to use, switch live from menu bar
- **Auto-mute** — mute Mac speakers, Android devices, Chromecasts during recording (macOS)
- **Menu bar app** — shows recording status and mic level, switch settings without restart (macOS)
- **Auto-start** — install as login item with automatic crash recovery (macOS)
- **Config validation** — invalid values are clamped to sane defaults with warnings

## Quick Start

### 1. Prerequisites

- **macOS** 10.13+ or **Windows** 10+
- Python 3.12+
- A Whisper provider: [Groq API key](https://console.groq.com/) (free tier available) **or** a local [whisper.cpp](https://github.com/ggerganov/whisper.cpp) server

### 2. Install

**Option A — pipx (recommended):**

```bash
# macOS — includes menu bar support
pipx install "whisper-dic[macos]"

# Windows
pipx install whisper-dic
```

Don't have pipx? Install it with `pip install --user pipx && pipx ensurepath`.

**Option B — pip:**

```bash
pip install "whisper-dic[macos]"    # macOS
pip install whisper-dic             # Windows
```

**Option C — from source:**

```bash
git clone https://github.com/timmeromberg/whisper-dic.git
cd whisper-dictation
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[macos]"          # Windows: pip install -e .
```

### 3. Configure

On first run, whisper-dic creates a config file at `~/.config/whisper-dic/config.toml` (macOS/Linux) or `%APPDATA%/whisper-dic/config.toml` (Windows) from the bundled template.

Edit it to set your provider:

```toml
[whisper]
provider = "groq"           # or "local"

[whisper.groq]
api_key = "gsk_your_key"    # get from console.groq.com
```

Or use the interactive setup (macOS only):

```bash
whisper-dic setup
```

### 4. Permissions

**macOS:** Grant these in **System Settings > Privacy & Security**:

| Permission | Why | What to add |
|---|---|---|
| **Microphone** | Audio recording | Your Terminal app (e.g. iTerm, Terminal) |
| **Accessibility** | Global hotkey + paste simulation | Your Terminal app **and** the Python binary whisper-dic runs with |

To find which Python binary to add, run:

```bash
python3 -c "import sys; print(sys.executable)"
```

Add the printed path to Accessibility. If you installed via pipx, the binary is inside `~/.local/pipx/venvs/whisper-dic/bin/python`. If you installed from source, it's `.venv/bin/python` in the repo.

**Important:** macOS will kill whisper-dic with a trace trap (SIGTRAP) if the Python binary doesn't have Accessibility permission. Make sure you're running whisper-dic with the same Python you granted permission to.

If permissions are missing, whisper-dic will show a notification telling you which one to fix.

**Windows:** No special permissions needed.

### 5. Run

```bash
# Menu bar mode (recommended, macOS only)
whisper-dic menubar

# Foreground mode (all platforms)
whisper-dic run
```

### 6. Test

Hold **Left Option** (macOS) or **Left Alt** (Windows), speak, release. Your words should appear at the cursor.

## Usage

### Hotkey Modifiers

| Hold | macOS | Windows | Behavior |
|------|-------|---------|----------|
| Dictate | **Left Option** | **Left Alt** | Transcribe and paste |
| Dictate + send | **Option + Ctrl** | **Alt + Ctrl** | Paste and press Return |
| Voice command | **Option + Shift** | **Alt + Shift** | Execute instead of paste |
| Cycle language | **Double-tap Option** | **Double-tap Alt** | Switch to next language |

### Voice Commands

Hold Option + Shift (macOS) or Alt + Shift (Windows) and say any of these:

| Say | macOS | Windows |
|-----|-------|---------|
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
| screenshot | Cmd+Ctrl+Shift+4 | *(macOS only)* |
| full screenshot | Cmd+Ctrl+Shift+3 | *(macOS only)* |

Common Whisper mishearings are handled automatically ("peace" -> "paste", "coffee" -> "copy", etc.).

### Text Commands

When enabled, spoken punctuation is converted automatically:

| Say | Inserts |
|-----|---------|
| period / full stop | . |
| comma | , |
| question mark | ? |
| exclamation mark / exclamation point | ! |
| new line | newline |
| new paragraph | blank line |
| open quote / close quote | curly quotes |
| open paren / close paren | ( / ) |
| colon / semicolon | : / ; |
| dash / em dash | — |
| hyphen | - |

## CLI Commands

```bash
whisper-dic run              # Start in foreground
whisper-dic menubar          # Start with menu bar icon (macOS only)
whisper-dic setup            # Interactive setup wizard (macOS only)
whisper-dic setup-local      # Install whisper.cpp server + model for local transcription
whisper-dic doctor           # Run diagnostic checks (config, provider, mic, permissions)
whisper-dic status           # Show config and endpoint health
whisper-dic provider [groq|local]  # Show or switch provider
whisper-dic set KEY VALUE    # Update a config value (run 'whisper-dic set -h' for examples)
whisper-dic devices          # List available microphones
whisper-dic logs             # Show recent log entries (use -n f to follow)
whisper-dic discover         # Find audio devices on your network
whisper-dic install          # Install as login item (macOS only)
whisper-dic uninstall        # Remove login item (macOS only)
whisper-dic version          # Show version
```

When installed via pip/pipx, `whisper-dic` is available as a command on all platforms.

## Configuration

All settings are in `config.toml` (at `~/.config/whisper-dic/config.toml`). See the bundled `config.example.toml` for the full reference.

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

### AI Rewriting

Use an LLM to clean up transcriptions (fix grammar, punctuation, capitalization). Requires a Groq API key (reuses your existing `whisper.groq.api_key`):

```toml
[rewrite]
enabled = true
model = "llama-3.3-70b-versatile"
# Customize rewriting behavior by changing this prompt
prompt = "You are a dictation assistant. Clean up the following transcription: fix grammar, punctuation, and capitalization. Keep the original meaning and words as much as possible. Return only the corrected text, nothing else."
```

On macOS, toggle AI rewriting live from the menu bar. When disabled, raw transcriptions are pasted as before.

### Live Preview

Show a floating text overlay with live transcription while you hold the dictation key. The preview updates every few seconds by transcribing the audio accumulated so far:

```toml
[recording]
streaming_preview = true
preview_interval = 3.0  # seconds between preview updates
```

**Note:** Each preview update sends a transcription request. On Groq's free tier (20 req/min), the default 3-second interval uses ~20 req/min. Increase the interval if you hit rate limits.

On macOS, toggle live preview from the menu bar.

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

### Microphone Selection

Choose which microphone to use (run `whisper-dic devices` to list available mics):

```toml
[recording]
device = "MacBook Pro Microphone"
```

Leave unset or remove the line to use the system default. On macOS, you can also switch microphones live from the menu bar.

### Custom Voice Commands

Map any spoken phrase to a keyboard shortcut:

```toml
[custom_commands]
"zoom in" = "cmd+="       # use "ctrl+=" on Windows
"zoom out" = "cmd+-"      # use "ctrl+-" on Windows
"next tab" = "ctrl+tab"
"close window" = "cmd+w"  # use "ctrl+w" on Windows
```

Use with Option + Shift (macOS) or Alt + Shift (Windows).

## Local Setup (whisper.cpp)

The local provider connects to a [whisper.cpp](https://github.com/ggml-org/whisper.cpp) server running an OpenAI-compatible API at `http://localhost:2022`. You need: a server binary and a model file.

### Automated Setup

The fastest way to get a local server running:

```bash
whisper-dic setup-local
```

This will:
1. Build the whisper-server binary from source (macOS/Linux) or download a prebuilt binary (Windows)
2. Download a Whisper model from Hugging Face (you choose the size)
3. Generate a start script
4. Update your config to use the local provider

On macOS, add `--autostart` to install as a login item:
```bash
whisper-dic setup-local --autostart
```

After setup, verify everything works:
```bash
whisper-dic doctor
```

### Manual Setup

#### macOS

```bash
# Install build tools
xcode-select --install
brew install cmake

# Clone and build
git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git
cd whisper.cpp
mkdir build && cd build
cmake .. -DWHISPER_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release -j

# Download a model
cd ..
curl -L -o models/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

# Start the server
./build/bin/whisper-server \
  --model models/ggml-large-v3-turbo.bin \
  --host 127.0.0.1 --port 2022 \
  --inference-path "/v1/audio/transcriptions" \
  --convert
```

#### Windows

1. Download `whisper-bin-x64.zip` from the [latest release](https://github.com/ggml-org/whisper.cpp/releases/latest)
2. Extract `whisper-server.exe`
3. Download a model from the table below
4. Run:
```cmd
whisper-server.exe --model ggml-large-v3-turbo.bin --host 127.0.0.1 --port 2022 --inference-path "/v1/audio/transcriptions" --convert
```

#### Linux

Same as macOS, but replace `xcode-select --install` with your distro's build tools:
```bash
# Debian/Ubuntu
sudo apt install build-essential cmake git

# Fedora
sudo dnf install gcc-c++ cmake git
```

### Models

| Model | Size | Quality | Speed |
|-------|------|---------|-------|
| tiny | 78 MB | Basic | Fastest |
| base | 148 MB | Decent | Fast |
| small | 488 MB | Good | Moderate |
| medium | 1.5 GB | Very good | Slower |
| large-v3 | 3.1 GB | Best accuracy | Slowest |
| **large-v3-turbo** | **1.6 GB** | **Near-best** | **Fast** |

**Recommendation:** `large-v3-turbo` — best tradeoff between accuracy and speed.

Download URL pattern: `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin`

### Verify

```bash
# Check if the server is running
curl http://localhost:2022/

# Run all diagnostics
whisper-dic doctor
```

## Auto-Start at Login (macOS)

```bash
# Install (creates launchd plist, starts at login, auto-restarts on crash)
whisper-dic install

# View logs
tail -f ~/Library/Logs/whisper-dictation.log

# Uninstall
whisper-dic uninstall
```

Not available on Windows. Use Task Scheduler or a startup shortcut instead.

## Menu Bar (macOS)

When running in menubar mode, the status bar icon shows:

| Icon | State |
|------|-------|
| 🎤 | Idle — ready to dictate |
| 🔴 + level bar | Recording — shows mic input level |
| ⏳ | Transcribing — sending audio to Whisper |

Click the icon to switch language, provider, microphone, hotkey, beep volume, or quit.

Not available on Windows — use `whisper-dic.bat run` for foreground mode.

## Troubleshooting

Run `whisper-dic doctor` for a quick diagnostic check of your setup.

**Hotkey not working?**
- macOS: Grant Accessibility permission in System Settings > Privacy & Security
- Windows: Make sure no other app is using Left Alt as a global hotkey
- Check the hotkey isn't used by another app

**Transcription failing?**
- Run `whisper-dic doctor` to check endpoint health and config
- Check logs: `tail -f ~/Library/Logs/whisper-dictation.log` (macOS) or check console output (Windows)
- For Groq: verify API key is set and valid

**Text not appearing?**
- macOS: Grant Accessibility permission (needed for Cmd+V simulation)
- Windows: Try running as administrator if paste simulation fails
- Make sure cursor is in a text field

**No start beep?**
- Check `audio_feedback.enabled = true` in config
- Increase `audio_feedback.volume`

**Long dictations failing intermittently?**
- Audio is compressed as FLAC before upload to minimize network errors
- Transient SSL errors are retried automatically (up to 3 times)
- If persistent, check your network connection

**Wrong microphone?**
- Run `whisper-dic devices` to see available mics
- Set `device` under `[recording]` in config.toml, or switch from the menu bar (macOS)

## Development

```bash
git clone https://github.com/timmeromberg/whisper-dic.git
cd whisper-dictation
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[macos]"    # macOS (or just `pip install -e .` on Windows)
pytest tests/ -v
```

## Project Structure

```
whisper-dictation/
├── src/whisper_dic/         # pip-installable package
│   ├── __init__.py          # package init, __version__
│   ├── __main__.py          # python -m whisper_dic support
│   ├── cli.py               # CLI commands, argparse, main()
│   ├── config.py            # config loading, validation, live-reload
│   ├── dictation.py         # core hold-to-dictate engine
│   ├── menubar.py           # menu bar UI (macOS only)
│   ├── recorder.py          # microphone capture
│   ├── transcriber.py       # Whisper API clients
│   ├── hotkey.py            # global hotkey listener
│   ├── doctor.py            # diagnostic checks (whisper-dic doctor)
│   ├── local_setup.py       # automated whisper.cpp setup (whisper-dic setup-local)
│   ├── commands.py          # voice command table
│   ├── cleaner.py           # text cleanup
│   ├── paster.py            # clipboard + paste
│   ├── history.py           # persistent transcription history
│   ├── overlay.py           # floating status overlay (macOS only)
│   ├── audio_control.py     # device muting
│   ├── log.py               # logging
│   ├── menu.py              # setup TUI (macOS only)
│   ├── VERSION              # semantic version
│   ├── config.example.toml  # bundled config template
│   └── compat/              # platform abstraction (macOS + Windows)
│       ├── _macos.py        # Quartz/AppKit backends
│       └── _windows.py      # Win32 backends
├── tests/                   # pytest test suite
├── pyproject.toml           # build config, dependencies, tool settings
├── whisper-dic              # dev wrapper (macOS/Linux)
└── whisper-dic.bat          # dev wrapper (Windows)
```

## License

MIT
