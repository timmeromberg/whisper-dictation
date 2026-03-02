# Configuration Reference

whisper-dic reads `config.toml` from:

- macOS/Linux: `~/.config/whisper-dic/config.toml`
- Windows: `%APPDATA%/whisper-dic/config.toml`

If the file does not exist, it is created automatically from `config.example.toml` on first run.

## Top-Level Sections

| Section | Purpose |
|---|---|
| `[hotkey]` | Dictation trigger key |
| `[recording]` | Recording limits, sample rate, live preview |
| `[whisper]` | Provider, language, timeout, failover, prompt |
| `[whisper.local]` | Local whisper.cpp endpoint/model |
| `[whisper.groq]` | Groq endpoint, model, API key |
| `[paste]` | Auto-send behavior |
| `[text_commands]` | Spoken punctuation conversion |
| `[audio_feedback]` | Start/stop beeps |
| `[audio_control]` | Auto-mute local/network devices |
| `[rewrite]` | AI rewrite settings |
| `[overlay]` | Overlay accessibility options |
| `[custom_commands]` | Custom spoken shortcuts |

## Hotkey

```toml
[hotkey]
key = "left_option"
```

Supported values:

- `left_option`
- `right_option`
- `left_command`
- `right_command`
- `left_shift`
- `right_shift`

## Whisper Provider

### Groq (cloud)

```toml
[whisper]
provider = "groq"

[whisper.groq]
api_key = "gsk_..."
model = "whisper-large-v3"
url = "https://api.groq.com/openai/v1/audio/transcriptions"
```

### Local (whisper.cpp)

```toml
[whisper]
provider = "local"

[whisper.local]
url = "http://localhost:2022/v1/audio/transcriptions"
model = "large-v3"
```

## Provider Failover

When enabled, whisper-dic tries the other provider if the primary fails.

```toml
[whisper]
failover = true
```

## Whisper Prompt

Use `prompt` to bias transcription toward domain terms:

```toml
[whisper]
prompt = "whisper-dic, PostgreSQL, AppKit"
```

## Languages

```toml
[whisper]
language = "en"
languages = ["en", "nl", "de"]
```

- `language` is the active language at startup.
- Double-tap the hotkey to cycle through `languages`.

## Recording Settings

```toml
[recording]
min_duration = 0.3
max_duration = 300.0
sample_rate = 16000
device = ""
streaming_preview = false
preview_interval = 3.0
preview_provider = ""
```

Notes:

- `min_duration`: short taps below this threshold are treated as language-cycle taps.
- `max_duration`: recordings longer than this are discarded.
- `sample_rate`: valid values are `8000`, `16000`, `22050`, `44100`, `48000`.
- `device`: microphone name from `whisper-dic devices`; empty means system default.
- `preview_interval`: clamped to `0.1` to `30.0` seconds.
- `preview_provider`: optional override (`"local"` or `"groq"`) for live preview.

## Paste Behavior

```toml
[paste]
auto_send = false
```

If `true`, whisper-dic presses Return after every paste. You can also trigger auto-send per dictation by holding `Option/Alt + Ctrl`.

## Text Commands

```toml
[text_commands]
enabled = true
```

When enabled, spoken punctuation and formatting phrases are converted automatically (for example `period`, `new line`, `question mark`).

## Audio Feedback

```toml
[audio_feedback]
enabled = true
start_frequency = 880
stop_frequency = 660
duration_seconds = 0.08
volume = 0.2
```

- `volume` is clamped to `0.0` to `1.0`.

## Audio Control (Auto-Mute)

```toml
[audio_control]
enabled = false
mute_local = true
```

### Network and custom devices

```toml
[[audio_control.devices]]
type = "adb"
name = "Android Tablet"
serial = ""
unmute_volume = 10

[[audio_control.devices]]
type = "chromecast"
name = "Living Room Speaker"

[[audio_control.devices]]
type = "upnp"
name = "Samsung TV"
location = "http://192.168.1.100:49152/description.xml"

[[audio_control.devices]]
type = "custom"
name = "My Device"
mute_command = "some-command --mute"
unmute_command = "some-command --unmute"
```

## AI Rewrite

```toml
[rewrite]
enabled = false
mode = "light"
model = "llama-3.3-70b-versatile"
prompt = "Rewrite this transcription in a professional tone."
```

- Uses Groq chat completions.
- Requires `whisper.groq.api_key`.
- `mode` options: `light`, `medium`, `full`, `custom`.
- `prompt` is only used when `mode = "custom"`.

### Per-App Context Prompts

whisper-dic detects the frontmost app and automatically uses a context-appropriate rewrite prompt. Five categories are supported:

| Category | Apps | Default behavior |
|----------|------|-----------------|
| **coding** | Terminals, VS Code, Cursor, Windsurf, JetBrains | Preserve technical terms, convert spoken code patterns (`dot py` → `.py`, `dash dash` → `--`) |
| **chat** | Slack, Discord, Teams, iMessage, Signal | Casual tone, minimal grammar fixes |
| **email** | Apple Mail, Outlook, Superhuman | Professional tone, proper grammar |
| **writing** | Notion, Obsidian, Apple Notes, Word | Full prose cleanup |
| **browser** | Safari, Chrome, Firefox, Arc, Edge | Balanced medium cleanup |

Each category can be enabled/disabled and given a custom prompt:

```toml
[rewrite.contexts.coding]
enabled = true
# prompt = "Your custom coding prompt here"

[rewrite.contexts.chat]
enabled = true

[rewrite.contexts.email]
enabled = true

[rewrite.contexts.writing]
enabled = true

[rewrite.contexts.browser]
enabled = true
```

If the frontmost app doesn't match any category, the global `mode`/`prompt` above is used. If a category is disabled, dictation in those apps falls back to the global prompt.

Platform note:

- macOS and Windows: frontmost-app detection is active.
- Linux: frontmost-app detection is not available in the fallback backend yet, so rewrite always uses the global `mode`/`prompt`.

## Live Preview

Live preview is controlled by `recording.streaming_preview`, `recording.preview_interval`, and optionally `recording.preview_provider`.

```toml
[recording]
streaming_preview = true
preview_interval = 3.0
preview_provider = "local"
```

Using Groq for preview can consume request quota quickly; local preview avoids that.

## Overlay Accessibility

These settings control the floating recording and preview overlays used by macOS menubar mode.

```toml
[overlay]
reduced_motion = false
high_contrast = false
font_scale = 1.0
```

- `reduced_motion`: disables pulsing/fade-heavy effects.
- `high_contrast`: increases text/background contrast.
- `font_scale`: preview text scaling; clamped to `0.75` to `2.0`.

The menu bar UI exposes these in **Accessibility**.

## Custom Voice Commands

```toml
[custom_commands]
"zoom in" = "cmd+="
"zoom out" = "cmd+-"
"next tab" = "ctrl+tab"
"close window" = "cmd+w"
```

Supported modifiers in shortcuts:

- `cmd`
- `ctrl`
- `shift`
- `alt`

Use custom commands with hotkey + Shift (voice command mode).
