"""Diagnostic checks for whisper-dic setup."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .compat import data_dir
from .config import AppConfig, load_config
from .transcriber import create_transcriber


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    fix: str


def check_config(config_path: Path) -> tuple[CheckResult, AppConfig | None]:
    """Check that the config file exists and parses."""
    if not config_path.exists():
        return CheckResult(
            name="Config file",
            passed=False,
            message=f"Not found: {config_path}",
            fix="Run 'whisper-dic setup' to create a config, or copy config.example.toml",
        ), None

    try:
        config = load_config(config_path)
    except Exception as exc:
        return CheckResult(
            name="Config file",
            passed=False,
            message=f"Parse error: {exc}",
            fix=f"Fix the TOML syntax in {config_path}",
        ), None

    return CheckResult(
        name="Config file",
        passed=True,
        message=str(config_path),
        fix="",
    ), config


def check_provider(config: AppConfig) -> CheckResult:
    """Check that the active provider endpoint is reachable."""
    provider = config.whisper.provider
    transcriber = create_transcriber(config.whisper)
    try:
        ok = transcriber.health_check()
    except Exception:
        ok = False
    finally:
        transcriber.close()

    if ok:
        url = config.whisper.local.url if provider == "local" else config.whisper.groq.url
        return CheckResult(
            name=f"Provider ({provider})",
            passed=True,
            message=f"Reachable at {url}",
            fix="",
        )

    if provider == "local":
        return CheckResult(
            name=f"Provider ({provider})",
            passed=False,
            message=f"Not reachable at {config.whisper.local.url}",
            fix="Start your whisper.cpp server, or run: whisper-dic setup-local",
        )

    return CheckResult(
        name=f"Provider ({provider})",
        passed=False,
        message=f"Not reachable at {config.whisper.groq.url}",
        fix="Check your internet connection and API key",
    )


def check_groq_api_key(config: AppConfig) -> CheckResult | None:
    """Check that Groq API key is set when needed. Returns None if not applicable."""
    needs_groq = config.whisper.provider == "groq" or config.whisper.failover
    if not needs_groq:
        return None

    key = config.whisper.groq.api_key.strip()
    if key:
        redacted = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
        return CheckResult(
            name="Groq API key",
            passed=True,
            message=f"Set ({redacted})",
            fix="",
        )

    return CheckResult(
        name="Groq API key",
        passed=False,
        message="Not set",
        fix="whisper-dic set whisper.groq.api_key gsk_YOUR_KEY",
    )


def check_microphone() -> CheckResult:
    """Check that at least one input device is available."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [d for d in devices if d["max_input_channels"] > 0]  # type: ignore[index]
        if not inputs:
            return CheckResult(
                name="Microphone",
                passed=False,
                message="No input devices found",
                fix="Connect a microphone and check system audio settings",
            )

        default_idx = sd.default.device[0]
        for d in inputs:
            if d["index"] == default_idx:  # type: ignore[index]
                return CheckResult(
                    name="Microphone",
                    passed=True,
                    message=str(d["name"]),  # type: ignore[index]
                    fix="",
                )

        return CheckResult(
            name="Microphone",
            passed=True,
            message=f"{len(inputs)} input device(s) available",
            fix="",
        )
    except Exception as exc:
        return CheckResult(
            name="Microphone",
            passed=False,
            message=str(exc),
            fix="Install sounddevice: pip install sounddevice",
        )


def check_accessibility() -> CheckResult | None:
    """Check macOS Accessibility permission. Returns None on other platforms."""
    if sys.platform != "darwin":
        return None

    try:
        from .compat import check_accessibility as _check

        missing = _check()
        if not missing:
            return CheckResult(
                name="Accessibility",
                passed=True,
                message="Granted",
                fix="",
            )

        return CheckResult(
            name="Accessibility",
            passed=False,
            message="Not granted",
            fix="System Settings > Privacy & Security > Accessibility — add whisper-dic",
        )
    except Exception as exc:
        return CheckResult(
            name="Accessibility",
            passed=False,
            message=str(exc),
            fix="Check macOS permissions in System Settings",
        )


def check_local_install() -> CheckResult:
    """Check if whisper-dic setup-local has been run."""
    data = data_dir()
    server_name = "whisper-server.exe" if sys.platform == "win32" else "whisper-server"
    server_path = data / "bin" / server_name
    models_dir = data / "models"

    if not server_path.exists():
        return CheckResult(
            name="Local install",
            passed=False,
            message="whisper-server not found",
            fix="Run 'whisper-dic setup-local' to install whisper.cpp locally",
        )

    model_files = list(models_dir.glob("ggml-*.bin")) if models_dir.exists() else []
    if not model_files:
        return CheckResult(
            name="Local install",
            passed=False,
            message="Server binary found but no model downloaded",
            fix="Run 'whisper-dic setup-local' to download a model",
        )

    model_names = ", ".join(f.stem.replace("ggml-", "") for f in model_files)
    return CheckResult(
        name="Local install",
        passed=True,
        message=f"Server + model(s): {model_names}",
        fix="",
    )


def run_doctor(config_path: Path) -> int:
    """Run all diagnostic checks and print results."""
    results: list[CheckResult] = []

    config_result, config = check_config(config_path)
    results.append(config_result)

    if config is not None:
        results.append(check_provider(config))

        api_key_result = check_groq_api_key(config)
        if api_key_result is not None:
            results.append(api_key_result)

    results.append(check_microphone())

    accessibility_result = check_accessibility()
    if accessibility_result is not None:
        results.append(accessibility_result)

    results.append(check_local_install())

    # Print results
    any_failed = False
    max_name_len = max(len(r.name) for r in results)

    for r in results:
        tag = "[ok]  " if r.passed else "[FAIL]"
        print(f"  {tag} {r.name:<{max_name_len}}  {r.message}")
        if not r.passed:
            any_failed = True
            print(f"         {'':>{max_name_len}}  -> {r.fix}")

    return 1 if any_failed else 0
