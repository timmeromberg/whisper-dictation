# Menu Bar (macOS)

The menubar UI is available on macOS only.

Start it with:

```bash
whisper-dic menubar
```

## Status Icons

| Icon | Meaning |
|---|---|
| `🎤` | Idle, ready to dictate |
| `🔴` + level bar | Recording in progress with live level meter |
| `⏳` | Transcribing |
| `⚠️` | Provider unreachable |

## Main Menu Features

### Language

- Shows active language.
- Lets you switch among configured `whisper.languages`.
- Updates `whisper.language` in config.

### Provider

- Switch between `local` and `groq`.
- Prompts for Groq API key if needed.
- Runs provider health checks after switching.

### Hotkey

- Change trigger key (`left_option`, `right_option`, `left_command`, `right_command`, `left_shift`, `right_shift`).
- Applied live without restart.

### Volume

- Slider for `audio_feedback.volume`.
- Persists back to config after short debounce.

### Microphone

- Choose system default or specific input device.
- Auto-refreshes when input devices change.
- Applied live without restart.

### Quick Toggles

Single-click on/off toggles for:

- Text Commands
- Auto-Send
- Audio Control
- Failover
- Live Preview

### AI Rewrite

- Enable/disable rewrite.
- Switch rewrite mode (`light`, `medium`, `full`, `custom`).
- Edit custom prompt.
- Change rewrite model.

### History

- Shows recent entries (up to 20 visible in menu).
- Click entry to copy to clipboard.
- Clear history from the menu.

### Recording Submenu

Editable runtime settings:

- Min Duration
- Max Duration
- Timeout
- Preview Interval
- Preview Provider

### Accessibility Submenu

Overlay settings mapped to `[overlay]` in config:

- Reduced Motion (`overlay.reduced_motion`)
- High Contrast (`overlay.high_contrast`)
- Text Size (`overlay.font_scale`)

Text size choices in menu are 85%, 100%, 125%, and 150%. Config supports a broader clamped range of `0.75` to `2.0`.

### Utility Items

- Groq API Key dialog
- Check Status
- View Logs
- How to Use helper
- Version display

### Getting Started Checklist

The menu bar includes a **Getting Started** checklist with actionable onboarding items:

- Check Permissions
- Set Provider
- Test Dictation
- Review Privacy

Behavior:

- Shows progress (`x/4`) directly in the menu title.
- Sends a one-time intro prompt after startup until dismissed.
- Supports **Dismiss Intro Prompt** and **Reset Checklist**.
- Progress is persisted in `menubar_onboarding.json` under your config directory.

### Contextual Tips

Lightweight tips are shown in key menu sections (Input, Output, Whisper, AI Rewrite) to improve discoverability without changing existing power-user flows.

## Auto-Start at Login

From CLI:

```bash
whisper-dic install
whisper-dic uninstall
```

From menu:

- **Service > Install (Start at Login)**
- **Service > Uninstall**

Install creates a launchd agent with keep-alive, so whisper-dic restarts after crashes and starts at login.

## First-Run Wizard

On first menubar launch (when config does not exist), whisper-dic runs a guided setup:

1. Provider selection (`groq` or `local`)
2. Optional Groq API key entry
3. Hotkey selection

## Live Reload Behavior

The menubar watches `config.toml` for external changes and applies updates live, including provider, language, hotkey, preview settings, rewrite settings, and overlay accessibility settings.

Related docs:

- [Configuration](configuration.md)
- [Commands](commands.md)
