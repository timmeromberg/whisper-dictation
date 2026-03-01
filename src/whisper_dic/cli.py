"""CLI entry point for whisper-dic."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import AppConfig, _to_toml_literal, load_config, set_config_value

_PID_FILE = Path("/tmp/whisper-dic.pid")


def _default_config_path() -> Path:
    """Return the default config path (~/.config/whisper-dic/config.toml)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / "whisper-dic" / "config.toml"


def _check_single_instance() -> bool:
    """Return True if no other instance is running. Writes PID file."""
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # check if process alive
            # Verify the process is actually whisper-dic (PID recycling)
            import subprocess as _sp
            result = _sp.run(["ps", "-p", str(pid), "-o", "comm="],
                             capture_output=True, text=True, timeout=3)
            if "whisper" in result.stdout.lower() or "python" in result.stdout.lower():
                print(f"[error] whisper-dic is already running (PID {pid}).")
                print("[error] Stop it first, or remove /tmp/whisper-dic.pid if stale.")
                return False
            # PID exists but is not whisper-dic — stale file
        except (ProcessLookupError, ValueError):
            pass  # stale PID file — overwrite
        except PermissionError:
            # PID file owned by another user — remove and recreate
            try:
                _PID_FILE.unlink()
            except OSError:
                pass

    try:
        _PID_FILE.write_text(str(os.getpid()))
    except PermissionError:
        print("[warning] Cannot write PID file, continuing without single-instance lock.")
        return True
    atexit.register(_cleanup_pid)
    return True


def _cleanup_pid() -> None:
    try:
        if _PID_FILE.exists() and _PID_FILE.read_text().strip() == str(os.getpid()):
            _PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _load_config_from_path(config_path: Path) -> AppConfig:
    if not config_path.exists():
        import shutil
        from importlib.resources import files
        example = files("whisper_dic").joinpath("config.example.toml")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(example), config_path)
        config_path.chmod(0o600)
        print(f"[setup] Created {config_path} from template. Edit it to set your preferences.")

    # Fix permissions if config is world-readable (it may contain API keys)
    mode = config_path.stat().st_mode & 0o777
    if mode & 0o044:
        config_path.chmod(0o600)
        print(f"[security] Fixed {config_path.name} permissions (was {oct(mode)}, now 0600).")

    return load_config(config_path)


def _print_status(config_path: Path, config: AppConfig) -> None:
    from . import __version__
    version = __version__
    print(f"[status] whisper-dic v{version}")
    print(f"[status] Config: {config_path}")
    print(f"[status] hotkey.key = {config.hotkey.key}")
    print(
        "[status] recording = "
        f"min_duration={config.recording.min_duration}, "
        f"max_duration={config.recording.max_duration}, "
        f"sample_rate={config.recording.sample_rate}"
    )
    print(
        "[status] whisper = "
        f"provider={config.whisper.provider}, "
        f"language={config.whisper.language}, "
        f"timeout_seconds={config.whisper.timeout_seconds}"
    )
    print(
        "[status] whisper.local = "
        f"url={config.whisper.local.url}, model={config.whisper.local.model}"
    )
    print(
        "[status] whisper.groq = "
        f"url={config.whisper.groq.url}, model={config.whisper.groq.model}, "
        f"api_key={'set' if config.whisper.groq.api_key.strip() else 'missing'}"
    )
    print(
        "[status] rewrite = "
        f"enabled={config.rewrite.enabled}, model={config.rewrite.model}"
    )


def _check_endpoint_reachability(config: AppConfig) -> tuple[bool, bool, bool]:
    from .transcriber import GroqWhisperTranscriber, LocalWhisperTranscriber, create_transcriber

    local = LocalWhisperTranscriber(
        url=config.whisper.local.url,
        language=config.whisper.language,
        model=config.whisper.local.model,
        timeout_seconds=config.whisper.timeout_seconds,
    )
    groq = GroqWhisperTranscriber(
        api_key=config.whisper.groq.api_key,
        url=config.whisper.groq.url,
        language=config.whisper.language,
        model=config.whisper.groq.model,
        timeout_seconds=config.whisper.timeout_seconds,
    )
    current = create_transcriber(config.whisper)

    try:
        local_ok = local.health_check()
        groq_ok = groq.health_check()
        current_ok = current.health_check()
    finally:
        local.close()
        groq.close()
        current.close()

    return local_ok, groq_ok, current_ok


def command_status(config_path: Path) -> int:
    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    _print_status(config_path, config)

    local_ok, groq_ok, current_ok = _check_endpoint_reachability(config)

    print(f"[status] local endpoint reachable: {'yes' if local_ok else 'no'}")
    print(f"[status] groq endpoint reachable: {'yes' if groq_ok else 'no'}")
    print(
        f"[status] active provider ({config.whisper.provider}) reachable: "
        f"{'yes' if current_ok else 'no'}"
    )

    return 0


def command_provider(config_path: Path, provider: str | None) -> int:
    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    if provider is None:
        print(config.whisper.provider)
        return 0

    if provider == "groq" and not config.whisper.groq.api_key.strip():
        try:
            entered_key = input("Groq API key missing. Enter API key (leave blank to cancel): ").strip()
        except EOFError:
            entered_key = ""

        if not entered_key:
            print("[config] Provider unchanged because no API key was provided.")
            return 1

        set_config_value(config_path, "whisper.groq.api_key", entered_key)
        print("[config] Stored whisper.groq.api_key.")

    set_config_value(config_path, "whisper.provider", provider)
    print(f"[config] whisper.provider set to '{provider}'.")
    return 0


def command_set(config_path: Path, key: str, value: str) -> int:
    try:
        _load_config_from_path(config_path)
        set_config_value(config_path, key, value)
    except Exception as exc:
        print(f"Failed to set '{key}': {exc}")
        return 1

    print(f"[config] Set {key} = {_to_toml_literal(value)}")
    return 0


def command_devices(config_path: Path) -> int:
    import sounddevice as sd

    config = _load_config_from_path(config_path)
    current = config.recording.device
    default_idx = sd.default.device[0]

    print("\nAvailable microphones:\n")
    for dev in sd.query_devices():
        if dev["max_input_channels"] > 0:  # type: ignore[index]
            name = dev["name"]  # type: ignore[index]
            idx = dev["index"]  # type: ignore[index]
            ch = dev["max_input_channels"]  # type: ignore[index]
            markers = []
            if idx == default_idx:
                markers.append("system default")
            if name == current:
                markers.append("active")
            suffix = f"  ({', '.join(markers)})" if markers else ""
            print(f"  {name} [{ch}ch]{suffix}")

    if current:
        print(f"\nConfigured: {current}")
    else:
        print("\nConfigured: System Default")
    print("Change via: whisper-dic set recording.device \"Device Name\"")
    return 0


def command_run(config_path: Path) -> int:
    if not _check_single_instance():
        return 1
    _rotate_log_if_needed()

    try:
        config = _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    try:
        from .dictation import DictationApp

        app = DictationApp(config)
    except Exception as exc:
        print(f"Failed to initialize app: {exc}")
        return 1

    def _handle_signal(signum: int, _frame: Any) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = str(signum)
        print(f"\n[signal] Received {name}.")
        app.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        return app.run()
    except KeyboardInterrupt:
        app.stop()
        return 0
    finally:
        app.stop()


def command_setup(config_path: Path) -> int:
    try:
        _load_config_from_path(config_path)
    except Exception as exc:
        print(exc)
        return 1

    try:
        from .menu import run_setup_menu
    except Exception as exc:
        print(f"Failed to load setup menu: {exc}")
        return 1

    try:
        action = run_setup_menu(config_path)
    except KeyboardInterrupt:
        print()
        return 0
    except Exception as exc:
        print(f"Setup failed: {exc}")
        return 1

    if action == "start":
        return command_run(config_path)
    return 0


if sys.platform == "darwin":
    _PLIST_LABEL = "com.whisper.dictation"
    _PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "com.whisper.dictation.plist"
    _LOG_PATH = str(Path.home() / "Library" / "Logs" / "whisper-dictation.log")
else:
    _PLIST_LABEL = None  # type: ignore[assignment]
    _PLIST_PATH = None  # type: ignore[assignment]
    _log_dir = Path.home() / "AppData" / "Local" / "whisper-dictation"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_PATH = str(_log_dir / "whisper-dictation.log")
_LOG_MAX_BYTES = 100 * 1024  # 100 KB
_LOG_KEEP_LINES = 1000


def _rotate_log_if_needed() -> None:
    """Truncate log file to last N lines if it exceeds size threshold."""
    log_path = Path(_LOG_PATH)
    try:
        if not log_path.exists() or log_path.stat().st_size <= _LOG_MAX_BYTES:
            return
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        log_path.write_text("\n".join(lines[-_LOG_KEEP_LINES:]) + "\n", encoding="utf-8")
        print(f"[log] Rotated log ({len(lines)} -> {_LOG_KEEP_LINES} lines)")
    except Exception:
        pass  # non-fatal


def _generate_plist() -> str:
    import shutil
    found = shutil.which("whisper-dic") or "whisper-dic"
    script_path = Path(found).resolve()
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{script_path}</string>
    <string>menubar</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{script_path.parent}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>{_LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>{_LOG_PATH}</string>
</dict>
</plist>
"""


def command_logs(lines_arg: str) -> int:
    log_path = Path(_LOG_PATH)
    if not log_path.exists():
        print(f"[logs] No log file yet at {log_path}")
        print("[logs] Start whisper-dic to create it.")
        return 1

    if sys.platform == "win32":
        # Windows: read with Python (no tail)
        try:
            n = int(lines_arg) if lines_arg.lower() != "f" else 50
        except ValueError:
            print(f"[logs] Invalid line count: {lines_arg}")
            return 1
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-n:]:
            print(line)
        if lines_arg.lower() == "f":
            print("[logs] Live follow (-n f) is not supported on Windows.")
        return 0

    if lines_arg.lower() == "f":
        os.execlp("tail", "tail", "-f", str(log_path))
    else:
        try:
            n = int(lines_arg)
        except ValueError:
            print(f"[logs] Invalid line count: {lines_arg}")
            return 1
        os.execlp("tail", "tail", f"-n{n}", str(log_path))

    return 0


def command_install() -> int:
    if _PLIST_PATH is None:
        print("[install] Auto-start installation is not yet supported on this platform.")
        print("[install] Run 'whisper-dic run' directly instead.")
        return 1

    if _PLIST_PATH.exists():
        print(f"[install] Already installed at {_PLIST_PATH}")
        print("[install] Run 'whisper-dic uninstall' first to reinstall.")
        return 1

    _PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_PATH.write_text(_generate_plist(), encoding="utf-8")
    print(f"[install] Created {_PLIST_PATH}")

    result = subprocess.run(["launchctl", "load", str(_PLIST_PATH)], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[install] launchctl load failed: {result.stderr.strip()}")
        return 1

    print("[install] Loaded into launchd. whisper-dic will start at login.")
    print(f"[install] Logs: {_LOG_PATH}")
    return 0


def command_uninstall() -> int:
    if _PLIST_PATH is None:
        print("[uninstall] Auto-start installation is not supported on this platform.")
        return 1

    if not _PLIST_PATH.exists():
        print("[uninstall] Not installed.")
        return 1

    subprocess.run(["launchctl", "unload", str(_PLIST_PATH)], capture_output=True, text=True)
    _PLIST_PATH.unlink()
    print(f"[uninstall] Removed {_PLIST_PATH}")
    print("[uninstall] whisper-dic will no longer start at login.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    config_parent = argparse.ArgumentParser(add_help=False)
    config_parent.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Path to config.toml",
    )

    parser = argparse.ArgumentParser(
        description="System-wide hold-to-dictate.",
        parents=[config_parent],
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "run",
        parents=[config_parent],
        help="Start dictation",
    )
    subparsers.add_parser(
        "setup",
        parents=[config_parent],
        help="Open interactive setup menu",
    )

    subparsers.add_parser(
        "doctor",
        parents=[config_parent],
        help="Run diagnostic checks",
    )
    setup_local_parser = subparsers.add_parser(
        "setup-local",
        parents=[config_parent],
        help="Install whisper.cpp server and model for local transcription",
    )
    setup_local_parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
        help="Model size to download (default: interactive prompt)",
    )
    setup_local_parser.add_argument(
        "--autostart",
        action="store_true",
        help="Install as login item (macOS only)",
    )
    subparsers.add_parser(
        "status",
        parents=[config_parent],
        help="Show current config and endpoint reachability",
    )

    provider_parser = subparsers.add_parser(
        "provider",
        parents=[config_parent],
        help="Show or set the whisper provider",
    )
    provider_parser.add_argument(
        "provider",
        nargs="?",
        choices=["local", "groq"],
        help="Provider to set",
    )

    set_parser = subparsers.add_parser(
        "set",
        parents=[config_parent],
        help="Set a config value",
        epilog=(
            "examples:\n"
            "  whisper-dic set whisper.language nl\n"
            "  whisper-dic set whisper.provider groq\n"
            "  whisper-dic set whisper.groq.api_key gsk_...\n"
            "  whisper-dic set hotkey.key right_option\n"
            "  whisper-dic set audio_feedback.volume 0.5\n"
            "  whisper-dic set text_commands.enabled false"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    set_parser.add_argument("key", help="Dotted key path (e.g. whisper.language)")
    set_parser.add_argument("value", help="Value to set")

    subparsers.add_parser(
        "menubar",
        parents=[config_parent],
        help="Run with menu bar icon",
    )
    subparsers.add_parser(
        "devices",
        parents=[config_parent],
        help="List available microphones",
    )
    subparsers.add_parser(
        "discover",
        parents=[config_parent],
        help="Discover audio devices on the local network",
    )
    logs_parser = subparsers.add_parser(
        "logs",
        help="Tail the log file",
    )
    logs_parser.add_argument(
        "-n", "--lines", default="50",
        help="Number of lines to show (default: 50, use 'f' to follow)",
    )
    subparsers.add_parser(
        "install",
        help="Install as login item (start at login, auto-restart)",
    )
    subparsers.add_parser(
        "uninstall",
        help="Remove login item",
    )
    subparsers.add_parser(
        "version",
        help="Show version",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    command = args.command or "run"

    if command == "run":
        return command_run(config_path)
    if command == "menubar":
        if sys.platform != "darwin":
            print("[menubar] Menu bar UI is only available on macOS.")
            print("[menubar] Use 'whisper-dic run' for CLI mode.")
            return 1
        from .menubar import run_menubar
        return run_menubar(config_path)
    if command == "doctor":
        from .doctor import run_doctor
        return run_doctor(config_path)
    if command == "setup-local":
        from .local_setup import run_setup_local
        return run_setup_local(config_path, args.model, args.autostart)
    if command == "setup":
        return command_setup(config_path)
    if command == "status":
        return command_status(config_path)
    if command == "provider":
        return command_provider(config_path, args.provider)
    if command == "set":
        return command_set(config_path, args.key, args.value)
    if command == "devices":
        return command_devices(config_path)
    if command == "discover":
        from .audio_control import discover
        discover(config_path)
        return 0
    if command == "logs":
        return command_logs(args.lines)
    if command == "install":
        return command_install()
    if command == "uninstall":
        return command_uninstall()
    if command == "version":
        from . import __version__
        print(__version__)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
