# whisper-dic

## Overview
macOS system-wide hold-to-dictate tool. Hold a hotkey, speak, release — text appears at the cursor. Uses Whisper (Groq cloud or local whisper.cpp) for transcription.

## Architecture
Single-process Python app with a rumps menu bar UI. pynput listens for global hotkeys on a background thread; the main thread runs the AppKit event loop.

### Key Files
| File | Purpose |
|------|---------|
| `whisper-dic` | Bash entry point, resolves symlinks, execs Python |
| `dictation.py` | Main app, CLI, config parsing, recording pipeline |
| `menubar.py` | rumps menu bar UI, settings switching |
| `recorder.py` | Microphone capture via sounddevice, FLAC output |
| `transcriber.py` | Whisper API clients (Groq, local) |
| `hotkey.py` | Global hotkey listener (pynput + Quartz) |
| `commands.py` | Voice command table (copy, paste, undo, etc.) |
| `cleaner.py` | Text cleanup, filler removal, punctuation commands |
| `paster.py` | Clipboard + Cmd+V simulation |
| `audio_control.py` | Device muting (local Mac, ADB, Chromecast, custom) |
| `log.py` | Timestamped logging |
| `menu.py` | Interactive setup TUI |

### Process Model
- **Foreground only** — backgrounding Python/AppKit from bash breaks GUI sessions, XPC connections, or Accessibility permissions on macOS. Run in terminal or use `./whisper-dic install` for launchd.
- **launchd** — `./whisper-dic install` creates a plist with `KeepAlive: true` for auto-start at login and crash recovery.
- **Logs** — `/tmp/whisper-dictation.log`

## Validation Commands
| Change Type | Command |
|-------------|---------|
| Run (foreground) | `./whisper-dic menubar` |
| Run (no menu bar) | `./whisper-dic run` |
| Check config | `./whisper-dic status` |
| Interactive setup | `./whisper-dic setup` |

## Submodule Versioning
- `VERSION` file at repo root (semver)
- **Patch** (0.1.x): fixes, tweaks, refactors, config
- **Minor** (0.x.0): new features, significant behavior changes
- **Major** (x.0.0): user direction only

## Known Issues
- **Intermittent SIGTRAP** — pynput's Quartz event tap occasionally crashes with `zsh: trace trap` on Apple Silicon + Python 3.14. Restarting usually resolves it. Not code-related.
- **Accessibility permission** — when running via launchd, the Python binary itself needs Accessibility permission (not just the terminal app).

## Config
- `config.toml` (gitignored) — user config created from `config.example.toml`
- Provider: Groq (cloud) or local whisper.cpp
- Hotkey, language, audio feedback, device muting all configurable
