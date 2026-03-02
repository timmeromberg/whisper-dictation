# Architecture

Technical reference for developers and AI coding agents working on whisper-dic.

## Pipeline Overview

```
Hotkey press
    |
    v
Recorder.start()  -->  sounddevice callback accumulates audio chunks
    |
    |  [optional: preview thread polls accumulated audio every 3s]
    |
Hotkey release
    |
    v
Recorder.stop()  -->  RecordingResult(audio_bytes, duration, sample_count)
    |
    v
Transcriber.transcribe(audio_bytes)  -->  raw transcript
    |  [retry with exponential backoff on transient errors]
    |  [failover to alternate provider if enabled]
    |
    v
TextCleaner.clean(transcript)  -->  cleaned text
    |  [filler removal, repeated words, text commands]
    |
    v
Rewriter.rewrite(cleaned, prompt_override)  -->  rewritten text  [optional]
    |  [context-aware prompt selected from frontmost app]
    |
    v
TextPaster.paste(text, auto_send, app_id)
    |  [copy to clipboard, simulate Cmd+V, restore clipboard]
    |
    v
TranscriptionHistory.add(text, language, duration)
```

## Module Map

### Core Pipeline

| Module | Purpose | Key Class |
|--------|---------|-----------|
| `dictation.py` | Orchestrator: hotkey events -> recording -> transcription -> paste | `DictationApp` |
| `recorder.py` | Microphone capture via sounddevice | `Recorder`, `RecordingResult` |
| `transcriber.py` | Whisper HTTP clients (local whisper.cpp + Groq) | `WhisperTranscriber` (ABC) |
| `cleaner.py` | Filler removal, text commands, punctuation fixes | `TextCleaner` |
| `rewriter.py` | LLM text enhancement via Groq chat completions | `Rewriter` |
| `paster.py` | Clipboard + simulated paste (Cmd+V / Ctrl+V) | `TextPaster` |
| `app_context.py` | Detect frontmost app, resolve rewrite category | `RewriteContext` |

### Input & Control

| Module | Purpose | Key Class |
|--------|---------|-----------|
| `hotkey.py` | Global hotkey detection (pynput + NSEvent) | `HotkeyListener`, `NSEventHotkeyListener` |
| `commands.py` | Voice command matching and execution | `execute()`, `_COMMANDS` table |
| `audio_control.py` | Auto-mute devices during recording | `AudioController` |

### Configuration & Persistence

| Module | Purpose | Key Class |
|--------|---------|-----------|
| `config.py` | TOML config loading, validation, atomic writes, hot-reload | `AppConfig`, `ConfigWatcher` |
| `history.py` | Transcription history (in-memory + JSON on disk) | `TranscriptionHistory` |

### UI (macOS only)

| Module | Purpose | Key Class |
|--------|---------|-----------|
| `menubar.py` | macOS menu bar app (rumps) | `DictationMenuBar` |
| `overlay.py` | Floating recording/preview overlays | `RecordingOverlay`, `PreviewOverlay` |
| `menu.py` | Interactive TUI setup menu | `run_setup_menu()` |

### Infrastructure

| Module | Purpose |
|--------|---------|
| `cli.py` | Entry point, argparse, 12+ CLI commands |
| `compat/` | Platform abstraction (macOS/Windows/Linux) |
| `log.py` | Timestamped logging to stdout |
| `doctor.py` | Diagnostic health checks |
| `local_setup.py` | Automated whisper.cpp installation |

## Threading Model

DictationApp manages several concurrent threads:

| Thread | Lifetime | Purpose |
|--------|----------|---------|
| Main thread | App lifetime | Config loading, event loop |
| Hotkey listener | App lifetime | Detects key press/release (pynput or NSEvent) |
| `hotkey-start` | Per press | Runs `_on_hold_start()` off the listener thread |
| `hotkey-end` | Per release | Runs `_on_hold_end()` off the listener thread |
| `dictation-pipeline` | Per dictation | Transcribe -> clean -> rewrite -> paste |
| `preview` | Per recording | Polls recorder for live preview (if enabled) |
| `beep` | Per beep | Non-blocking audio feedback |
| `config-watcher` | App lifetime | Polls config mtime every 5s |
| sounddevice callback | Per recording | Accumulates audio chunks into buffer |

Key synchronization:
- `_pipeline_lock` prevents concurrent transcriptions
- `_transcriber_lock` (RLock) serializes transcriber access during config hot-reload
- `_start_done` event prevents hold_end from racing ahead of hold_start
- `_preview_stop` event signals preview thread to exit

## Platform Abstraction (`compat/`)

The `compat/` package exports a unified API. Each platform has its own implementation file.

| Function | macOS | Windows | Linux |
|----------|-------|---------|-------|
| `frontmost_app_id()` | osascript (bundle ID) | ctypes (exe name) | no-op |
| `modifier_is_pressed(mask)` | Quartz CGEventSource | GetAsyncKeyState | no-op |
| `post_key(vk, flags)` | Quartz CGEvent | SendInput | no-op |
| `notify(msg, title)` | osascript | print (fallback) | print |
| `play_wav_file(path)` | afplay | winsound | sox/aplay |
| `check_accessibility()` | AXIsProcessTrusted | [] | [] |

Platform detection happens at import time in `compat/__init__.py`.

## Context-Aware Rewriting

When rewrite is enabled, the pipeline resolves the frontmost app before acquiring the pipeline lock:

1. `frontmost_app_id()` returns bundle ID (macOS) or exe name (Windows)
2. `app_context.category_for_app(app_id)` maps it to a category: `coding`, `chat`, `email`, `writing`, `browser`, or `None`
3. `rewriter.prompt_for_context()` selects the system prompt:
   - Category with custom user prompt in config -> use that prompt
   - Category without custom prompt -> use built-in category prompt from `CONTEXT_PROMPTS`
   - No category (unknown app) -> fall back to global rewrite mode/prompt

Categories can be individually disabled in config (`[rewrite.contexts.<category>]`).

## Configuration System

Config lives at `~/.config/whisper-dic/config.toml` (Linux/macOS) or `%APPDATA%/whisper-dic/config.toml` (Windows).

**Loading:** `load_config()` reads TOML, maps sections to typed dataclasses, validates ranges (clamps out-of-bounds values with warnings).

**Writing:** `set_config_value()` uses atomic writes: write to temp file in same directory, `fsync`, then `os.replace`. Preserves file permissions.

**Hot-reload:** `ConfigWatcher` runs a background thread polling file mtime every 5s. On external change (not from our own writes, debounced by 2s), it reloads and calls the `on_change` callback. The menubar uses this to update UI state without restart.

## Error Handling Strategy

The pipeline never crashes. Every stage has fallback behavior:

| Stage | On failure |
|-------|-----------|
| Recording start | Reset audio backend, retry once. If still fails, notify user and return to idle. |
| Transcription | Retry up to 4x with exponential backoff (0.5s, 1s, 2s, capped 8s). Then failover to alternate provider if enabled. |
| Cleanup | Use raw transcript |
| Rewrite | Use cleaned (pre-rewrite) text |
| Paste | Log error, return to idle |

User-facing error messages are derived from exception text in `_actionable_error()` (maps HTTP status codes, connection errors, timeouts to plain-English guidance).

## Entry Points

```bash
whisper-dic run          # CLI daemon: HotkeyListener + DictationApp
whisper-dic menubar      # macOS menu bar: rumps + NSEventHotkeyListener + DictationApp
whisper-dic setup-local  # Install whisper.cpp server + model
whisper-dic doctor       # Diagnostic health checks
whisper-dic status       # Show config + endpoint reachability
whisper-dic set K V      # Update config value
```

The `menubar` entry point uses `NSEventHotkeyListener` instead of pynput's `HotkeyListener` because pynput's CGEventTap causes SIGTRAP on macOS 14+ when called from background threads. NSEvent monitors run on the main thread via the rumps (AppKit) run loop.

## Common Extension Points

| Task | Where to edit |
|------|---------------|
| Add a new hotkey option | `hotkey.py` `KEY_MAP` + `_NS_KEYCODE_MAP` |
| Add a voice command | `commands.py` `_COMMANDS` dict |
| Add an app to a rewrite category | `app_context.py` `_MACOS_APP_CATEGORIES` / `_WINDOWS_APP_CATEGORIES` |
| Add a rewrite context category | `rewriter.py` `CONTEXT_PROMPTS` + `app_context.py` `CATEGORIES` |
| Add a text command | `cleaner.py` `_TEXT_COMMANDS` list |
| Add a CLI command | `cli.py` add subparser + handler function |
| Add platform support | `compat/_<platform>.py` implementing the exported API |
| Add a config section | `config.py` add dataclass + parse in `load_config()` |
