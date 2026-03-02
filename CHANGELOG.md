# Changelog

All notable changes to whisper-dic are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.3] - 2026-03-02

### Fixed
- Microphone recovery after sleep/wake — PortAudio backend is re-initialized on macOS wake and on recording failure with automatic retry
- Coding context rewrite no longer shortens or summarizes dictated messages
- Questions in coding context are preserved as questions instead of being flattened into statements

### Added
- Sleep/wake microphone recovery tests (13 new test cases covering reset, retry logic, and wake observer)

## [0.10.2] - 2026-03-02

### Fixed
- Made per-app context pipeline tests platform-agnostic so CI matrix runs (Linux/Windows/macOS) validate rewrite behavior consistently
- Removed macOS-only app-ID assumptions from new context tests that caused false CI failures outside macOS
- Hardened smoke-test recorder/dictation checks to gracefully skip recorder-dependent assertions when another live instance already owns the audio device

## [0.10.1] - 2026-03-02

### Fixed
- Release workflow now runs from the tested commit SHA and verifies both CI and E2E succeeded for that exact SHA before publishing
- PR E2E gate now uses the fast smoke path only (full Linux/macOS/Windows E2E remain on push/manual runs)
- Menubar config hot-reload now applies `rewrite.contexts.*` toggle changes live in UI state
- Smoke mode now hard-disables clipboard and keyboard injection in `TextPaster`, preventing accidental paste side effects during smoke checks

### Added
- New dictation pipeline tests for per-app rewrite context prompt selection and app-id passthrough
- New menubar tests covering context menu sync and config-reload context toggle propagation

### Changed
- Coverage gate raised from 34% to 35% in CI
- Cross-platform docs and metadata now explicitly reflect Linux support and current per-app context behavior
- README now includes an explicit privacy/data-handling section, including local-model guidance and history persistence notes

## [0.10.0] - 2026-03-02

### Added
- Per-app context-aware AI rewriting — automatically adapts rewrite prompt based on frontmost app (coding, chat, email, writing, browser)
- Spoken code pattern handling in coding context (`dot py` → `.py`, `dash dash` → `--`)
- App Contexts submenu in menu bar for per-category enable/disable toggles
- `[rewrite.contexts.*]` config sections for per-category customization
- Automated GitHub release and PyPI publish on every successful CI push to main

### Changed
- Pipeline captures frontmost app once and passes to both rewriter and paster (eliminates redundant osascript call)

## [0.9.14] - 2026-03-02

### Fixed
- Smoke test startup now runs in explicit no-input mode to prevent pre-commit smoke runs from registering live hotkeys or pasting into the active app
- Menubar startup path now supports `WHISPER_DIC_SMOKE_NO_INPUT` to skip listener/timer/input hooks while still validating startup wiring
- Added regression coverage to ensure smoke-mode startup bypasses health/input hooks and normal startup remains unchanged

## [0.9.13] - 2026-03-02

### Changed
- Linux CI now provisions an integration harness (`xvfb`, audio libs) and runs the full pytest suite under virtual display
- E2E workflow now runs on all pull requests to ensure required E2E checks are always present

### Added
- Linux compatibility backend (`whisper_dic.compat._linux`) so shared modules can be imported/tested on Linux
- Security CI now uploads machine-readable artifacts (`bandit-report.json`, `pip-audit-report.json`, `pip-audit-sbom.json`)
- Branch protection required-check enforcement for `main` (CI, security, and PR E2E checks required before merge)

## [0.9.12] - 2026-03-02

### Fixed
- Dispatched all rumps/AppKit state mutations (title, menu items, timers) to main thread via `callAfter` to fix segfault on recording start
- Enabled `faulthandler` for better crash diagnostics on segfaults

### Changed
- Removed mic level bar from preview overlay
- Split README into landing page (~150 lines) + 7 reference docs in `docs/`

### Added
- Overlay accessibility settings (reduced motion, high contrast, font scale)
- Updating and uninstalling instructions in README

## [0.9.11] - 2026-03-02

### Fixed
- Synchronized preview-transcriber lifecycle so config/menu changes cannot close or swap it while preview transcription is in flight
- Hardened POSIX runtime state fallback directory checks (private mode + ownership validation) and removed hardcoded temp path usage
- Updated contributor guidance to match the repository's versioned changelog + `VERSION` bump workflow

### Changed
- CI now validates on Linux in PRs (lint/type plus Linux-safe test subset in the matrix)
- Linux full E2E now runs on pull requests in addition to pushes
- Coverage step now enforces a non-regression threshold (`--cov-fail-under=34`)

### Added
- Dedicated CI security job with Bandit (medium/high) and dependency audit (`pip-audit`)
- Regression tests for secure state-dir fallback behavior and preview-transcriber swap synchronization

## [0.9.10] - 2026-03-02

### Fixed
- Serialized transcriber access across dictation pipeline and config hot-reload to avoid swap/close races with in-flight transcriptions
- Routed remaining menubar config-reload overlay/rewrite label UI updates through main-thread dispatch paths
- Hardened history copy action to gracefully handle `pbcopy` failures and timeouts
- Made config writes atomic to prevent partial/corrupt `config.toml` on interruption
- Clarified cross-platform contributor setup instructions (macOS extras vs Windows/manual setup)
- Pinned CI/E2E/release GitHub Actions to immutable SHAs for supply-chain hardening

### Added
- Fast PR-gated E2E smoke workflow path (`scripts/e2e-pr-smoke.sh`) with local mock endpoint validation
- Regression tests for atomic config writes, transcriber swap synchronization, and menubar thread-safety helpers

## [0.9.9] - 2026-03-02

### Fixed
- Restored `Recorder` incremental-audio cache fields and snapshot path to keep streaming-preview tests green across Python 3.13 CI
- Passed `GITHUB_TOKEN` to macOS and Linux E2E runs so `setup-local` avoids GitHub API rate-limit failures when resolving whisper.cpp releases

## [0.9.8] - 2026-03-02

### Fixed
- Hardened single-instance PID lock to use a per-user state directory instead of a shared global temp path
- Stopped preview thread during shutdown before closing transcriber resources
- Tightened config permission hardening to enforce owner-only access when any group/other bits are set
- Local model downloads now resolve/check against an immutable Hugging Face revision SHA instead of moving `main`
- History default persistence path now uses `%APPDATA%` on Windows for consistency with config location
- `whisper-dic setup` now clearly guards non-macOS usage with an actionable message
- Corrected source checkout directory names in README examples
- Corrected CONTRIBUTING pre-commit wording to match repository reality
- Updated Code of Conduct reporting channel guidance

### Added
- CI coverage visibility step (`pytest-cov`) on macOS Python 3.12
- Regression tests for PID pathing, setup platform guard, config permission tightening, pinned model revision URLs, history default paths, and preview shutdown lifecycle

## [0.9.7] - 2026-03-02

### Fixed
- Race condition on quick hotkey press — recording could get stuck forever
- UI mutations from background threads now dispatched to main thread (AppKit crash fix)
- PID file handles recycled PIDs and permission errors
- API keys redacted from error log messages
- Clipboard restore delay increased for Electron apps (VS Code, Slack)
- Beeps in command/auto-send mode no longer overlap
- Mute/unmute race condition fixed with threading lock
- Chromecast discovery timeout prevents blocking forever
- UPnP aiohttp session leak fixed

### Added
- Config hot-reload for min/max duration, sample rate, timeout, prompt, languages, custom commands
- History file permissions set to 0600 on write

## [0.9.6] - 2026-03-02

### Added
- Auto-refresh microphone menu when devices are connected/disconnected (5s polling)

### Fixed
- AudioController fully recreated on config changes (was only toggling enabled flag)

## [0.9.5] - 2026-03-02

### Changed
- Windows E2E: removed unnecessary cmake and git from choco install (saves ~2.5 min)

## [0.9.4] - 2026-03-01

### Added
- GitHub Actions caching for whisper-server binary and model in E2E tests

## [0.9.3] - 2026-03-01

### Added
- End-to-end test suite with 53 assertions across Linux, macOS, and Windows
- Docker-based E2E testing for Linux
- GitHub Actions E2E workflow for all 3 platforms

## [0.9.2] - 2026-03-01

### Added
- Preview overlay: fade animation, language badge, elapsed time, progress dots
- Pulsing recording dot with mic level bar in overlay
- `whisper-dic doctor` diagnostic command
- `whisper-dic setup-local` for automated local whisper.cpp installation

## [0.9.1] - 2026-03-01

### Added
- Separate preview provider setting (use local for preview, groq for final)
- Auto-sizing preview overlay with status badges
- Press Escape while recording to cancel dictation

### Changed
- Preview interval minimum lowered to 0.1s

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
