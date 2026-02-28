"""CLI entry point for whisper-dic."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

from config import AppConfig, _to_toml_literal, load_config, set_config_value
from dictation import DictationApp
from transcriber import GroqWhisperTranscriber, LocalWhisperTranscriber, create_transcriber

_PID_FILE = Path("/tmp/whisper-dic.pid")


def _check_single_instance() -> bool:
    """Return True if no other instance is running. Writes PID file."""
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
            os.kill(pid, 0)  # check if process alive
            print(f"[error] whisper-dic is already running (PID {pid}).")
            print("[error] Stop it first, or remove /tmp/whisper-dic.pid if stale.")
            return False
        except (ProcessLookupError, ValueError):
            pass  # stale PID file — overwrite

    _PID_FILE.write_text(str(os.getpid()))
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
        example = config_path.parent / "config.example.toml"
        if example.exists():
            import shutil
            shutil.copy2(example, config_path)
            config_path.chmod(0o600)
            print(f"[setup] Created {config_path.name} from template. Edit it to set your preferences.")
        else:
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Run: cp config.example.toml config.toml"
            )

    # Fix permissions if config is world-readable (it may contain API keys)
    mode = config_path.stat().st_mode & 0o777
    if mode & 0o044:
        config_path.chmod(0o600)
        print(f"[security] Fixed {config_path.name} permissions (was {oct(mode)}, now 0600).")

    return load_config(config_path)


def _print_status(config_path: Path, config: AppConfig) -> None:
    version_file = Path(__file__).with_name("VERSION")
    version = version_file.read_text().strip() if version_file.exists() else "unknown"
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


def _check_endpoint_reachability(config: AppConfig) -> tuple[bool, bool, bool]:
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
        from menu import run_setup_menu
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


_PLIST_LABEL = "com.whisper.dictation"
_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"
_LOG_PATH = str(Path.home() / "Library" / "Logs" / "whisper-dictation.log")
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
    script_path = Path(__file__).resolve().parent / "whisper-dic"
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

    if lines_arg.lower() == "f":
        import os
        os.execlp("tail", "tail", "-f", str(log_path))
    else:
        try:
            n = int(lines_arg)
        except ValueError:
            print(f"[logs] Invalid line count: {lines_arg}")
            return 1
        import os
        os.execlp("tail", "tail", f"-n{n}", str(log_path))

    return 0


def command_install() -> int:
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
        default=str(Path(__file__).with_name("config.toml")),
        help="Path to config.toml",
    )

    parser = argparse.ArgumentParser(
        description="System-wide hold-to-dictate for macOS.",
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
        from menubar import run_menubar
        return run_menubar(config_path)
    if command == "setup":
        return command_setup(config_path)
    if command == "status":
        return command_status(config_path)
    if command == "provider":
        return command_provider(config_path, args.provider)
    if command == "set":
        return command_set(config_path, args.key, args.value)
    if command == "discover":
        from audio_control import discover
        discover(config_path)
        return 0
    if command == "logs":
        return command_logs(args.lines)
    if command == "install":
        return command_install()
    if command == "uninstall":
        return command_uninstall()
    if command == "version":
        version_file = Path(__file__).with_name("VERSION")
        print(version_file.read_text().strip() if version_file.exists() else "unknown")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
