# Development

For contribution workflow details, see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Development Setup

```bash
git clone https://github.com/timmeromberg/whisper-dic.git
cd whisper-dic
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[macos]"          # Windows/Linux: pip install -e .
```

Create or verify config:

```bash
whisper-dic status
```

## Test and Quality Commands

```bash
# unit tests
pytest

# coverage (optional)
pytest --cov=src/whisper_dic --cov-report=term-missing

# lint
ruff check src/ tests/

# type checks
mypy src/whisper_dic/

# smoke/e2e helpers
bash scripts/smoke-test.sh
bash scripts/e2e-test.sh
```

## Pre-commit Hooks

The repository does not currently enforce a mandatory `.pre-commit-config.yaml`.

A practical local hook baseline is:

1. `ruff check src/ tests/`
2. `mypy src/whisper_dic/`
3. `pytest`

## Project Structure

```text
whisper-dictation/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml
│       ├── e2e.yml
│       └── release.yml
├── docs/
│   ├── commands.md
│   ├── configuration.md
│   ├── development.md
│   ├── local-setup.md
│   ├── menubar.md
│   ├── privacy.md
│   └── troubleshooting.md
├── scripts/
│   ├── e2e-pr-smoke.sh
│   ├── e2e-test.sh
│   └── smoke-test.sh
├── src/whisper_dic/
│   ├── __init__.py
│   ├── __main__.py
│   ├── VERSION
│   ├── audio_control.py
│   ├── cleaner.py
│   ├── cli.py
│   ├── commands.py
│   ├── config.example.toml
│   ├── config.py
│   ├── dictation.py
│   ├── doctor.py
│   ├── history.py
│   ├── hotkey.py
│   ├── local_setup.py
│   ├── log.py
│   ├── menu.py
│   ├── menubar.py
│   ├── overlay.py
│   ├── paster.py
│   ├── recorder.py
│   ├── rewriter.py
│   ├── transcriber.py
│   └── compat/
│       ├── __init__.py
│       ├── _macos.py
│       └── _windows.py
├── tests/
│   ├── conftest.py
│   ├── test_audio_control.py
│   ├── test_cleaner.py
│   ├── test_cli.py
│   ├── test_cli_runtime.py
│   ├── test_commands.py
│   ├── test_compat.py
│   ├── test_config.py
│   ├── test_history.py
│   ├── test_hotkey.py
│   ├── test_local_setup.py
│   ├── test_log.py
│   ├── test_menubar.py
│   ├── test_paster.py
│   ├── test_recorder.py
│   ├── test_rewriter.py
│   ├── test_streaming_preview.py
│   ├── test_transcriber.py
│   └── e2e/
│       └── test_audio.flac
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml
├── whisper-dic
└── whisper-dic.bat
```

## Notes

- `whisper-dic` is the macOS/Linux wrapper script.
- `whisper-dic.bat` is the Windows wrapper.
- macOS menubar and setup UX live in `menubar.py` and `menu.py`.
- Core dictation pipeline is in `dictation.py`.
