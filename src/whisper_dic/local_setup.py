"""Automated local whisper.cpp server installation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx

from .config import set_config_value

# ---------------------------------------------------------------------------
# Data directory
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """Platform-appropriate data directory for whisper-dic."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "whisper-dic"


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

MODELS: dict[str, dict[str, str | int]] = {
    "tiny":            {"file": "ggml-tiny.bin",            "size_mb": 78},
    "base":            {"file": "ggml-base.bin",            "size_mb": 148},
    "small":           {"file": "ggml-small.bin",           "size_mb": 488},
    "medium":          {"file": "ggml-medium.bin",          "size_mb": 1530},
    "large-v3":        {"file": "ggml-large-v3.bin",        "size_mb": 3100},
    "large-v3-turbo":  {"file": "ggml-large-v3-turbo.bin",  "size_mb": 1620},
}

HF_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
WHISPER_CPP_REPO = "https://github.com/ggml-org/whisper.cpp.git"

# launchd
_LOCAL_SERVER_LABEL = "com.whisper-dic.local-server"


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _print_progress(label: str, downloaded: int, total: int) -> None:
    if total > 0:
        pct = downloaded * 100 // total
        dl_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        bar_len = 30
        filled = bar_len * downloaded // total
        bar = "=" * filled + ">" + " " * (bar_len - filled - 1)
        print(f"\r  [{bar}] {pct:3d}% ({dl_mb:.0f}/{total_mb:.0f} MB) {label}", end="", flush=True)
    else:
        dl_mb = downloaded / (1024 * 1024)
        print(f"\r  {dl_mb:.0f} MB downloaded — {label}", end="", flush=True)


def _download_file(url: str, dest: Path, label: str) -> None:
    """Download a file with progress indicator. Atomic via .part rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")

    with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with part.open("wb") as f:
            for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                _print_progress(label, downloaded, total)

    part.rename(dest)
    print()  # newline after progress bar


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------

def _download_model(data_dir: Path, model_name: str) -> Path:
    info = MODELS[model_name]
    model_file = str(info["file"])
    model_path = data_dir / "models" / model_file

    if model_path.exists():
        print(f"  Model {model_file} already downloaded, skipping.")
        return model_path

    size_mb = info["size_mb"]
    print(f"  Downloading {model_file} ({size_mb} MB)...")
    url = f"{HF_BASE_URL}/{model_file}"
    _download_file(url, model_path, model_file)
    return model_path


# ---------------------------------------------------------------------------
# Server binary: platform-specific
# ---------------------------------------------------------------------------

def _require_command(name: str, install_hint: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"'{name}' not found. {install_hint}")


def _acquire_server_build(data_dir: Path) -> Path:
    """Build whisper-server from source (macOS / Linux)."""
    bin_dir = data_dir / "bin"
    server_path = bin_dir / "whisper-server"

    if server_path.exists():
        print("  whisper-server binary already exists, skipping build.")
        return server_path

    _require_command("git", "Install git: https://git-scm.com/downloads")
    _require_command("cmake", "Install cmake: brew install cmake (macOS) or apt install cmake (Linux)")

    src_dir = data_dir / "src" / "whisper.cpp"
    if not src_dir.exists():
        print("  Cloning whisper.cpp...")
        subprocess.run(
            ["git", "clone", "--depth", "1", WHISPER_CPP_REPO, str(src_dir)],
            check=True,
        )
    else:
        print("  Updating whisper.cpp...")
        subprocess.run(["git", "pull"], cwd=src_dir, check=True)

    build_dir = src_dir / "build"
    build_dir.mkdir(exist_ok=True)

    print("  Building whisper-server (this may take a few minutes)...")
    subprocess.run(
        ["cmake", "..", "-DWHISPER_BUILD_SERVER=ON", "-DCMAKE_BUILD_TYPE=Release"],
        cwd=build_dir, check=True,
    )
    subprocess.run(
        ["cmake", "--build", ".", "--config", "Release", "-j"],
        cwd=build_dir, check=True,
    )

    built = build_dir / "bin" / "whisper-server"
    if not built.exists():
        raise RuntimeError(f"Build succeeded but {built} not found. Check cmake output.")

    bin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, server_path)
    server_path.chmod(0o755)
    print(f"  Built: {server_path}")
    return server_path


def _resolve_latest_release_asset(asset_name: str) -> str:
    """Find download URL for a GitHub release asset."""
    response = httpx.get(
        "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest",
        headers={"Accept": "application/vnd.github.v3+json"},
        follow_redirects=True,
        timeout=30.0,
    )
    response.raise_for_status()
    for asset in response.json().get("assets", []):
        if asset["name"] == asset_name:
            return str(asset["browser_download_url"])
    raise RuntimeError(
        f"Asset '{asset_name}' not found in latest whisper.cpp release. "
        "Check https://github.com/ggml-org/whisper.cpp/releases"
    )


def _acquire_server_windows(data_dir: Path) -> Path:
    """Download prebuilt whisper-server.exe from GitHub releases."""
    bin_dir = data_dir / "bin"
    server_path = bin_dir / "whisper-server.exe"

    if server_path.exists():
        print("  whisper-server.exe already exists, skipping download.")
        return server_path

    print("  Finding latest whisper.cpp release...")
    zip_url = _resolve_latest_release_asset("whisper-bin-x64.zip")

    tmp_dir = data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / "whisper-bin-x64.zip"

    print("  Downloading whisper-server...")
    _download_file(zip_url, zip_path, "whisper-bin-x64.zip")

    print("  Extracting whisper-server.exe + DLLs...")
    bin_dir.mkdir(parents=True, exist_ok=True)
    found = False
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            basename = Path(name).name
            if not basename:
                continue  # skip directory entries
            # Extract server exe and all DLLs it depends on
            if basename == "whisper-server.exe" or basename.endswith(".dll"):
                dest_file = bin_dir / basename
                with zf.open(name) as src, dest_file.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if basename == "whisper-server.exe":
                    found = True

    zip_path.unlink(missing_ok=True)
    tmp_dir.rmdir()

    if not found:
        raise RuntimeError("whisper-server.exe not found in the release archive")

    print(f"  Extracted: {server_path}")
    return server_path


# ---------------------------------------------------------------------------
# Start script generation
# ---------------------------------------------------------------------------

def _create_start_script_unix(data_dir: Path, server_path: Path, model_path: Path) -> Path:
    script_path = data_dir / "start-server.sh"
    script_path.write_text(
        "#!/bin/bash\n"
        "# whisper-dic local server — generated by: whisper-dic setup-local\n"
        "\n"
        f'exec "{server_path}" \\\n'
        f'    --model "{model_path}" \\\n'
        "    --host 127.0.0.1 \\\n"
        "    --port 2022 \\\n"
        '    --inference-path "/v1/audio/transcriptions" \\\n'
        "    --convert \\\n"
        "    --print-progress\n"
    )
    script_path.chmod(0o755)
    return script_path


def _create_start_script_windows(data_dir: Path, server_path: Path, model_path: Path) -> Path:
    script_path = data_dir / "start-server.bat"
    script_path.write_text(
        "@echo off\n"
        "REM whisper-dic local server — generated by: whisper-dic setup-local\n"
        "\n"
        f'"{server_path}" ^\n'
        f'    --model "{model_path}" ^\n'
        "    --host 127.0.0.1 ^\n"
        "    --port 2022 ^\n"
        '    --inference-path "/v1/audio/transcriptions" ^\n'
        "    --convert ^\n"
        "    --print-progress\n"
    )
    return script_path


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

def _install_launchd(server_path: Path, model_path: Path) -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{_LOCAL_SERVER_LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
        '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{_LOCAL_SERVER_LABEL}</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        f"    <string>{server_path}</string>\n"
        "    <string>--model</string>\n"
        f"    <string>{model_path}</string>\n"
        "    <string>--host</string>\n"
        "    <string>127.0.0.1</string>\n"
        "    <string>--port</string>\n"
        "    <string>2022</string>\n"
        "    <string>--inference-path</string>\n"
        "    <string>/v1/audio/transcriptions</string>\n"
        "    <string>--convert</string>\n"
        "  </array>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>KeepAlive</key>\n"
        "  <true/>\n"
        "  <key>StandardOutPath</key>\n"
        "  <string>/tmp/whisper-dic-server.log</string>\n"
        "  <key>StandardErrorPath</key>\n"
        "  <string>/tmp/whisper-dic-server.log</string>\n"
        "</dict>\n"
        "</plist>\n"
    )

    subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    print(f"  Installed launchd service: {_LOCAL_SERVER_LABEL}")
    print("  Logs: /tmp/whisper-dic-server.log")


# ---------------------------------------------------------------------------
# Interactive model picker
# ---------------------------------------------------------------------------

def _prompt_model_choice() -> str:
    print("\nAvailable models:\n")
    options = list(MODELS.keys())
    for i, name in enumerate(options, 1):
        info = MODELS[name]
        size = int(info["size_mb"])
        size_str = f"{size / 1000:.1f} GB" if size >= 1000 else f"{size} MB"
        rec = " (recommended)" if name == "large-v3-turbo" else ""
        print(f"  {i}. {name:<18} {size_str:>8}{rec}")

    print()
    while True:
        try:
            choice = input("Select model [1-6, default=6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(1)
        if not choice:
            return "large-v3-turbo"
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            if choice in MODELS:
                return choice
        print(f"  Invalid choice. Enter 1-{len(options)}.")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_setup_local(config_path: Path, model: str | None, autostart: bool) -> int:
    """Install whisper.cpp server and model for local transcription."""
    data_dir = _data_dir()

    # Step 1: Model selection
    if model is None:
        model = _prompt_model_choice()
    if model not in MODELS:
        print(f"  Unknown model '{model}'. Choose from: {', '.join(MODELS)}")
        return 1

    print(f"\n[setup-local] Data directory: {data_dir}")

    # Step 2: Acquire server binary
    print("\n[setup-local] Step 1/4 — Server binary")
    try:
        if sys.platform == "win32":
            server_path = _acquire_server_windows(data_dir)
        else:
            server_path = _acquire_server_build(data_dir)
    except Exception as exc:
        print(f"\n  Failed to acquire whisper-server: {exc}")
        print("  See manual setup: https://github.com/ggml-org/whisper.cpp")
        return 1

    # Step 3: Download model
    print("\n[setup-local] Step 2/4 — Model download")
    try:
        model_path = _download_model(data_dir, model)
    except Exception as exc:
        print(f"\n  Failed to download model: {exc}")
        return 1

    # Step 4: Create start script
    print("\n[setup-local] Step 3/4 — Start script")
    if sys.platform == "win32":
        script_path = _create_start_script_windows(data_dir, server_path, model_path)
    else:
        script_path = _create_start_script_unix(data_dir, server_path, model_path)
    print(f"  Created: {script_path}")

    # Step 5: Optional launchd auto-start (macOS only)
    if autostart and sys.platform == "darwin":
        print("\n[setup-local] Step 3b — Auto-start")
        _install_launchd(server_path, model_path)

    # Step 6: Update config
    print("\n[setup-local] Step 4/4 — Config update")
    try:
        set_config_value(config_path, "whisper.provider", "local")
        set_config_value(config_path, "whisper.local.url", "http://localhost:2022/v1/audio/transcriptions")
        print("  Set whisper.provider = local")
    except Exception as exc:
        print(f"  Config update failed: {exc}")
        print("  You can set it manually: whisper-dic set whisper.provider local")

    # Summary
    print("\n[setup-local] Done!")
    print(f"  Server:  {server_path}")
    print(f"  Model:   {model_path}")
    print(f"  Script:  {script_path}")
    if not autostart or sys.platform != "darwin":
        print(f"\n  To start the server:  {script_path}")
    print("  To verify:            whisper-dic doctor")

    return 0
