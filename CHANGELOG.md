# Changelog

All notable changes to whisper-dic are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-03-01

### Added
- Live transcription preview: see text appearing in a floating overlay while recording
- Periodic batch transcription of accumulated audio during recording
- Configurable preview interval (`recording.preview_interval`, default 4s)
- Menu bar toggle for Live Preview (macOS)

## [0.8.0] - 2026-03-01

### Added
- AI rewriting: optional LLM-powered cleanup of transcriptions via Groq chat completions
- Configurable rewrite prompt in `[rewrite]` config section
- Menu bar toggle for AI rewriting (macOS)
- Rewrite status shown in `whisper-dic status` output

## [0.7.1] - 2026-03-01

### Fixed
- Menubar config template lookup now uses package data instead of sibling file
- mypy type error in plist generation (shutil.which returns str)
- simple_term_menu added back to macOS optional deps and mypy ignore list

## [0.7.0] - 2026-03-01

### Added
- pip/pipx installable: `pipx install whisper-dic` or `pip install whisper-dic`
- macOS extras: `pipx install "whisper-dic[macos]"` for menu bar support
- `python -m whisper_dic` support
- Auto-created config at `~/.config/whisper-dic/config.toml` on first run

### Changed
- Restructured source into `src/whisper_dic/` package (src layout)
- All intra-package imports converted to relative imports
- Config path default changed from repo-relative to XDG config directory
- `pyproject.toml` now defines build-system, entry points, and all dependencies
- Removed `requirements.txt` (pyproject.toml is the single source of truth)
- Minimum Python version raised to 3.12
- CI installs via `pip install -e .` instead of `requirements.txt`

## [0.6.1] - 2026-03-01

### Fixed
- "new tab" voice command now sends Cmd+T (was incorrectly sending Cmd+Tab / app switcher)
- Default hotkey fallback corrected to `left_option` (was `right_option` when config section absent)
- Voice commands table: redo on Windows is Ctrl+Shift+Z (not Ctrl+Y)
- Screenshot/full screenshot voice commands marked macOS-only (no Windows equivalent)
- Text commands table: added missing open/close paren, hyphen, exclamation point
- Configure step in README now shows Windows `copy` command

## [0.6.0] - 2026-03-01

### Added
- Microphone selection: choose which input device to use for recording
- Menu bar submenu lists all available microphones with live switching
- `whisper-dic devices` CLI command to list available microphones
- Smoke test gracefully skips menubar startup when another instance is running

### Fixed
- Clipboard restored after paste to prevent accidental double-paste

### Changed
- Audio feedback (beeps) now non-blocking for lower dictation latency
- Recording starts immediately on keypress instead of waiting for beep

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
