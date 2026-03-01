# Changelog

All notable changes to whisper-dic are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-03-01

### Added
- Windows support (MVP): hold-to-dictate, voice commands, clipboard paste all work on Windows
- `compat/` platform abstraction package with macOS and Windows backends
- `whisper-dic.bat` entry point for Windows
- Windows CI via GitHub Actions (macos-latest + windows-latest matrix)

### Changed
- All platform-specific code (Quartz, osascript, afplay, launchctl) moved to `compat/_macos.py`
- Key simulation uses Win32 `SendInput` on Windows, CGEvent on macOS
- Modifier detection uses `GetAsyncKeyState` on Windows, Quartz on macOS
- Paste shortcut: Ctrl+V on Windows, Cmd+V on macOS
- `requirements.txt` uses platform markers for macOS-only dependencies

## [0.4.0] - 2026-03-01

### Added
- mypy type checking configuration with full codebase compliance
- pytest suite (73 tests) covering cleaner, commands, history, and config
- pyproject.toml with ruff lint and pytest configuration
- Config validation: invalid values clamped to sane ranges with warnings
- Persistent transcription history (saved to `~/.config/whisper-dic/history.json`)
- Log rotation on startup when log exceeds 100 KB
- PID file (`/tmp/whisper-dic.pid`) to prevent duplicate instances

### Changed
- Extracted `config.py` from `dictation.py` (config loading, validation, live-reload)
- Extracted `cli.py` from `dictation.py` (CLI commands, argparse, main entry point)
- Refactored menubar submenu builders into separate methods
- `dictation.py` now contains only `DictationApp` (472 lines, down from 1221)
- Updated README with all new features and project structure

### Fixed
- Overlay dispatched to main thread; UI callbacks made crash-safe
- Hold callbacks run off pynput thread to unblock key release events

## [0.3.0] - 2026-02-28

### Added
- Floating dot overlay indicator during recording (red) and transcribing (orange)
- Transcription history with menubar submenu and clipboard copy
- Custom voice commands via `[custom_commands]` config section
- Multi-provider failover with menu bar toggle
- Double-tap hotkey to cycle language (replaces single quick-tap)
- Actionable error messages for all failure types (401, 429, timeout, etc.)
- Whisper `prompt` parameter for vocabulary biasing
- First-run setup wizard for new users
- Smoke test suite (`scripts/smoke-test.sh`) with 11 checks
- Pre-commit hook running lint, compile, and smoke test
- Periodic health checks with exponential backoff
- Config file watching with live-reload on external changes
- Service management submenu (install/uninstall from menu bar)
- Recording settings submenu with input dialogs
- Groq API key dialog and provider health check in menu bar
- Voice/text command reference in help menu
- Retry transcription on transient network errors (SSL, connection reset)

### Fixed
- Audio muting moved to background thread to prevent segfault
- Mute after recording starts to avoid CoreAudio/PortAudio crash
- Beeps played via afplay instead of sounddevice to eliminate PortAudio crash
- Removed microphone pre-flight check that crashed with sounddevice conflict
- Use notifications instead of alerts for permission checks

## [0.2.0] - 2026-02-28

### Added
- macOS menu bar icon with full settings UI (provider, language, hotkey, volume slider)
- Voice commands via Option + Shift (copy, paste, undo, redo, screenshot, etc.)
- Aliases for common Whisper mishearings (peace → paste, coffee → copy, etc.)
- Text commands (period, comma, new line, new paragraph, etc.)
- Auto-send mode via hotkey + Ctrl (context-sensitive: terminals/IDEs only)
- Install/uninstall commands for launch-at-login via launchd
- Audio device auto-mute during recording (local Mac, ADB, Chromecast, UPnP, custom)
- Device discovery command (`whisper-dic discover`)
- FLAC compression before upload to minimize network errors
- Timestamped logging across all modules
- Volume control slider in menu bar
- Language cycling with double-tap and macOS notification
- Left-side modifier key support, default changed to left_option
- Interactive TUI settings menu

### Changed
- CLI command renamed to `whisper-dic`
- Auto-send uses per-press Ctrl modifier instead of global toggle

### Fixed
- Control key timing measured from release with 500ms window
- Python dock icon hidden in menubar mode
- Launch at login uses menubar mode
- osascript injection hardened, shell=True removed
- Config file permissions auto-fixed to 0600
- Logarithmic scale for mic level meter

## [0.1.0] - 2026-02-28

### Added
- System-wide hold-to-dictate for macOS
- Local whisper.cpp and Groq cloud provider support
- CLI with provider switching (`whisper-dic provider local|groq`)
- Regex-based filler word removal (um, uh, basically, you know, etc.)
- Clipboard paste via simulated Cmd+V
