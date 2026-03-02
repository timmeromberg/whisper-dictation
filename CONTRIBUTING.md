# Contributing to whisper-dic

Thanks for your interest in contributing! This guide will help you get started.

## Prerequisites

- Python 3.12+
- macOS 10.13+, Windows 10+, or Linux
- A Whisper provider: [Groq API key](https://console.groq.com/) (free) or a local [whisper.cpp](https://github.com/ggerganov/whisper.cpp) server

## Development Setup

```bash
# Clone the repo
git clone https://github.com/timmeromberg/whisper-dic.git
cd whisper-dic

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install in editable mode
pip install -e ".[macos]"   # macOS
# pip install -e .          # Windows/Linux

# Create your config (if you don't have one)
whisper-dic setup           # macOS interactive setup
# whisper-dic provider       # Windows/Linux/manual setup bootstrap
# whisper-dic set KEY VALUE  # all platforms
```

## Running Tests

```bash
# Unit tests
pytest

# Coverage (optional, mirrors CI visibility check)
pytest --cov=src/whisper_dic --cov-report=term-missing

# Linting
ruff check src/ tests/

# Type checking
mypy src/whisper_dic/

# Smoke test (macOS only — tests real startup + pipeline)
bash scripts/smoke-test.sh
```

Run these checks before opening a PR.

## Optional Pre-commit Hooks

If you want local commit-time checks, install and configure pre-commit in your environment. The repository does not currently ship a mandatory pre-commit hook configuration.

## Making Changes

### Branch workflow

1. Fork the repo and clone your fork
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes
4. Ensure all tests pass (see above)
5. Commit with a descriptive message (see style below)
6. Push and open a Pull Request

### Commit message style

Use imperative mood, lowercase (except proper nouns):

```
fix: race condition on quick press
feat: add microphone auto-refresh
docs: update README with new config options
chore: bump version to 0.9.7
perf: cache whisper model in CI
test: add e2e tests for Windows
```

Prefix with a scope when useful: `fix(audio):`, `feat(menubar):`, `test(e2e):`.

### What makes a good PR

- **One logical change per PR** — don't bundle unrelated fixes
- **Tests** — add or update tests for behavioral changes
- **CHANGELOG + VERSION** — bump `src/whisper_dic/VERSION` and add a versioned changelog entry at the top for user-facing changes
- **Description** — explain *why*, not just *what*

## Project Structure

```
src/whisper_dic/
  cli.py          # CLI entry point, argparse
  config.py       # Config loading, validation, live-reload
  dictation.py    # Core hold-to-dictate engine
  recorder.py     # Microphone capture
  transcriber.py  # Whisper API clients (local + Groq)
  paster.py       # Clipboard + simulated paste
  hotkey.py       # Global hotkey listener
  menubar.py      # macOS menu bar app (rumps)
  commands.py     # Voice command execution
  cleaner.py      # Text cleanup + filler removal
  audio_control.py # Auto-mute devices during recording
  compat/         # Platform abstraction (macOS/Windows/Linux fallback)
tests/            # pytest suite
scripts/          # Smoke test, E2E test
```

## Need Help?

- Ask in [Discussions](https://github.com/timmeromberg/whisper-dic/discussions) for questions and ideas
- Open an [issue](https://github.com/timmeromberg/whisper-dic/issues) for bugs or feature requests
- Check existing issues for things to work on — look for `good first issue` labels
