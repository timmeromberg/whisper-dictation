"""Automated local whisper.cpp server installation."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from .compat import data_dir as _data_dir
from .config import set_config_value

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

HF_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve"
HF_TREE_URL = "https://huggingface.co/api/models/ggerganov/whisper.cpp/tree"
HF_MODEL_INFO_URL = "https://huggingface.co/api/models/ggerganov/whisper.cpp"
WHISPER_CPP_REPO = "https://github.com/ggml-org/whisper.cpp.git"
WHISPER_CPP_RELEASE_URL = "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest"
_ALLOW_INSECURE_DOWNLOADS_ENV = "WHISPER_DIC_ALLOW_INSECURE_DOWNLOADS"

# launchd
_LOCAL_SERVER_LABEL = "com.whisper-dic.local-server"


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    sha256: str | None


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str
    assets: dict[str, ReleaseAsset]


def _allow_insecure_downloads() -> bool:
    val = os.environ.get(_ALLOW_INSECURE_DOWNLOADS_ENV, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _parse_sha256_digest(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().lower()
    if raw.startswith("sha256:"):
        raw = raw.split(":", 1)[1]
    if re.fullmatch(r"[0-9a-f]{64}", raw):
        return raw
    return None


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _assert_integrity(label: str, expected_sha256: str | None, actual_sha256: str) -> None:
    expected = _parse_sha256_digest(expected_sha256)
    if expected is None:
        if _allow_insecure_downloads():
            print(f"  [security] Warning: no checksum for {label}; continuing due {_ALLOW_INSECURE_DOWNLOADS_ENV}=1")
            return
        raise RuntimeError(
            f"Missing checksum for {label}. "
            f"Set {_ALLOW_INSECURE_DOWNLOADS_ENV}=1 to bypass (not recommended)."
        )
    if actual_sha256 != expected:
        raise RuntimeError(f"Checksum mismatch for {label}: expected {expected}, got {actual_sha256}")

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


def _download_file(url: str, dest: Path, label: str, expected_sha256: str | None = None) -> None:
    """Download a file with progress indicator. Atomic via .part rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    hasher = hashlib.sha256()

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=600.0) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with part.open("wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    _print_progress(label, downloaded, total)

        actual_sha256 = hasher.hexdigest()
        _assert_integrity(label, expected_sha256, actual_sha256)
        part.rename(dest)
        print()  # newline after progress bar
        print(f"  Verified SHA256 for {label}: {actual_sha256[:12]}...")
    except Exception:
        part.unlink(missing_ok=True)
        raise


def _resolve_hf_revision() -> str:
    """Resolve the current immutable commit SHA for ggerganov/whisper.cpp on HF."""
    response = httpx.get(HF_MODEL_INFO_URL, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    sha = str(payload.get("sha", "")).strip().lower() if isinstance(payload, dict) else ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("Could not resolve immutable Hugging Face revision SHA.")
    return sha


def _resolve_model_checksums(revision: str) -> dict[str, str]:
    """Resolve model SHA256 checksums from Hugging Face metadata."""
    response = httpx.get(f"{HF_TREE_URL}/{revision}?recursive=1", follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    checksums: dict[str, str] = {}
    payload = response.json()
    if not isinstance(payload, list):
        return checksums
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        lfs = entry.get("lfs")
        if not isinstance(path, str) or not isinstance(lfs, dict):
            continue
        sha = _parse_sha256_digest(str(lfs.get("oid", "")))
        if sha:
            checksums[path] = sha
    return checksums


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------

def _download_model(data_dir: Path, model_name: str) -> Path:
    info = MODELS[model_name]
    model_file = str(info["file"])
    model_path = data_dir / "models" / model_file

    try:
        revision = _resolve_hf_revision()
    except Exception as exc:
        if _allow_insecure_downloads():
            revision = "main"
            print(
                "  [security] Warning: could not resolve immutable HF revision "
                f"({exc}); using moving ref 'main' due {_ALLOW_INSECURE_DOWNLOADS_ENV}=1"
            )
        else:
            raise RuntimeError(
                "Could not resolve immutable Hugging Face revision for model download."
            ) from exc

    try:
        checksums = _resolve_model_checksums(revision)
    except Exception as exc:
        if _allow_insecure_downloads():
            checksums = {}
            print(
                "  [security] Warning: could not resolve model checksums "
                f"({exc}); continuing due {_ALLOW_INSECURE_DOWNLOADS_ENV}=1"
            )
        else:
            raise RuntimeError("Could not resolve model checksums from Hugging Face metadata.") from exc
    expected_sha = checksums.get(model_file)

    if expected_sha is None and not _allow_insecure_downloads():
        raise RuntimeError(
            f"Could not resolve checksum for {model_file}. "
            f"Set {_ALLOW_INSECURE_DOWNLOADS_ENV}=1 to bypass (not recommended)."
        )

    if model_path.exists():
        actual_sha = _sha256_file(model_path)
        try:
            _assert_integrity(model_file, expected_sha, actual_sha)
            print(f"  Model {model_file} already downloaded and verified, skipping.")
            return model_path
        except RuntimeError:
            print(f"  Existing model failed checksum verification, re-downloading: {model_file}")
            model_path.unlink(missing_ok=True)

    size_mb = info["size_mb"]
    print(f"  Downloading {model_file} ({size_mb} MB)...")
    url = f"{HF_BASE_URL}/{revision}/{model_file}"
    _download_file(url, model_path, model_file, expected_sha256=expected_sha)
    return model_path


# ---------------------------------------------------------------------------
# Server binary: platform-specific
# ---------------------------------------------------------------------------

def _require_command(name: str, install_hint: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"'{name}' not found. {install_hint}")


def _acquire_server_build(data_dir: Path, release_tag: str) -> Path:
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
        print(f"  Cloning whisper.cpp ({release_tag})...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", release_tag, WHISPER_CPP_REPO, str(src_dir)],
            check=True,
        )
    else:
        print(f"  Updating whisper.cpp to {release_tag}...")
        subprocess.run(["git", "fetch", "--depth", "1", "origin", release_tag], cwd=src_dir, check=True)
        subprocess.run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=src_dir, check=True)

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


def _resolve_latest_release() -> ReleaseInfo:
    """Resolve latest whisper.cpp release metadata and asset checksums."""
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.get(
        WHISPER_CPP_RELEASE_URL,
        headers=headers,
        follow_redirects=True,
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    tag_name = str(payload.get("tag_name", "")).strip()
    if not tag_name:
        raise RuntimeError("Could not resolve whisper.cpp release tag from GitHub API.")

    assets: dict[str, ReleaseAsset] = {}
    for raw in payload.get("assets", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        url = str(raw.get("browser_download_url", "")).strip()
        if not name or not url:
            continue
        assets[name] = ReleaseAsset(
            name=name,
            url=url,
            sha256=_parse_sha256_digest(str(raw.get("digest", ""))),
        )
    return ReleaseInfo(tag_name=tag_name, assets=assets)


def _acquire_server_windows(data_dir: Path, release: ReleaseInfo) -> Path:
    """Download prebuilt whisper-server.exe from GitHub releases."""
    bin_dir = data_dir / "bin"
    server_path = bin_dir / "whisper-server.exe"

    if server_path.exists():
        print("  whisper-server.exe already exists, skipping download.")
        return server_path

    print(f"  Using whisper.cpp release {release.tag_name}...")
    asset = release.assets.get("whisper-bin-x64.zip")
    if asset is None:
        raise RuntimeError(
            "Asset 'whisper-bin-x64.zip' not found in latest whisper.cpp release. "
            "Check https://github.com/ggml-org/whisper.cpp/releases"
        )

    tmp_dir = data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / "whisper-bin-x64.zip"

    print("  Downloading whisper-server...")
    _download_file(asset.url, zip_path, asset.name, expected_sha256=asset.sha256)

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

    print("\n[setup-local] Resolving trusted release metadata...")
    try:
        release = _resolve_latest_release()
        print(f"  whisper.cpp release: {release.tag_name}")
    except Exception as exc:
        print(f"  Failed to resolve release metadata: {exc}")
        if _allow_insecure_downloads():
            print(f"  Continuing due {_ALLOW_INSECURE_DOWNLOADS_ENV}=1")
            release = ReleaseInfo(tag_name="main", assets={})
        else:
            return 1

    # Step 2: Acquire server binary
    print("\n[setup-local] Step 1/4 — Server binary")
    try:
        if sys.platform == "win32":
            server_path = _acquire_server_windows(data_dir, release)
        else:
            server_path = _acquire_server_build(data_dir, release.tag_name)
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
