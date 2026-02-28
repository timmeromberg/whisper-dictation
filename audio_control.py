"""Auto-mute/unmute audio devices during recording."""

from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Protocol

from log import log


class AudioDevice(Protocol):
    """Interface for a mutable audio device."""
    name: str
    def mute(self) -> None: ...
    def unmute(self) -> None: ...


class LocalMacDevice:
    """Mute/unmute the local Mac's speakers via osascript."""

    def __init__(self) -> None:
        self.name = "Local Mac"
        self._was_muted = False
        self._saved_volume: int | None = None

    def mute(self) -> None:
        # Save current state before muting
        try:
            r = subprocess.run(
                ["osascript", "-e", "get volume settings"],
                capture_output=True, text=True, timeout=5,
            )
            # Output: "output volume:69, input volume:50, alert volume:100, output muted:false"
            parts = dict(p.strip().split(":") for p in r.stdout.strip().split(","))
            self._was_muted = parts.get("output muted", "").strip() == "true"
            self._saved_volume = int(parts.get("output volume", "50").strip())
            log("audio_ctrl", f"Saved Mac volume: {self._saved_volume}, was_muted: {self._was_muted}")
        except Exception as exc:
            log("audio_ctrl", f"Failed to save Mac volume: {exc}")
            self._was_muted = False
            self._saved_volume = None

        subprocess.run(
            ["osascript", "-e", "set volume output muted true"],
            capture_output=True, timeout=5,
        )
        log("audio_ctrl", "Muted: Local Mac")

    def unmute(self) -> None:
        if self._was_muted:
            log("audio_ctrl", "Mac was already muted, not restoring")
            return

        subprocess.run(
            ["osascript", "-e", "set volume output muted false"],
            capture_output=True, timeout=5,
        )
        if self._saved_volume is not None:
            # Restore exact volume level
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {self._saved_volume}"],
                capture_output=True, timeout=5,
            )
            log("audio_ctrl", f"Unmuted: Local Mac (restored volume {self._saved_volume})")
        else:
            log("audio_ctrl", "Unmuted: Local Mac")


class CustomDevice:
    """Mute/unmute via user-configured shell commands."""

    def __init__(self, name: str, mute_command: str, unmute_command: str) -> None:
        self.name = name
        self._mute_cmd = mute_command
        self._unmute_cmd = unmute_command

    def mute(self) -> None:
        try:
            subprocess.run(
                self._mute_cmd, shell=True,
                capture_output=True, timeout=10,
            )
            log("audio_ctrl", f"Muted: {self.name}")
        except Exception as exc:
            log("audio_ctrl", f"Mute failed for {self.name}: {exc}")

    def unmute(self) -> None:
        try:
            subprocess.run(
                self._unmute_cmd, shell=True,
                capture_output=True, timeout=10,
            )
            log("audio_ctrl", f"Unmuted: {self.name}")
        except Exception as exc:
            log("audio_ctrl", f"Unmute failed for {self.name}: {exc}")


def _adb_devices() -> list[tuple[str, str]]:
    """Return list of (serial, model) for connected ADB devices."""
    try:
        result = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        devices = []
        for line in result.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                model = ""
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1]
                        break
                devices.append((serial, model or serial))
        return devices
    except Exception:
        return []


class AdbDevice:
    """Mute/unmute an Android device connected via ADB (WiFi or USB)."""

    def __init__(self, name: str = "", serial: str = "", unmute_volume: int = 10) -> None:
        self.name = name or "Android Device"
        self._serial = serial  # empty = auto-detect first device
        self._unmute_volume = unmute_volume  # fallback if query fails
        self._saved_volume: int | None = None

    def _get_serial(self) -> str | None:
        if self._serial:
            return self._serial
        devices = _adb_devices()
        if devices:
            serial, model = devices[0]
            log("audio_ctrl", f"Auto-detected ADB device: {model} ({serial})")
            return serial
        return None

    def _run_adb(self, *args: str) -> subprocess.CompletedProcess | None:
        serial = self._get_serial()
        if not serial:
            log("audio_ctrl", f"No ADB device found for {self.name}")
            return None
        cmd = ["adb", "-s", serial] + list(args)
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except Exception as exc:
            log("audio_ctrl", f"ADB command failed for {self.name}: {exc}")
            return None

    def _query_volume(self) -> int | None:
        """Query current media stream volume. Returns int or None on failure."""
        result = self._run_adb("shell", "cmd", "media_session", "volume", "--get", "--stream", "3")
        if result is None:
            return None
        # Output contains a line like: "volume is 6 in range [0..15]"
        m = re.search(r"volume is (\d+)", result.stdout)
        if m:
            return int(m.group(1))
        log("audio_ctrl", f"Could not parse ADB volume output: {result.stdout.strip()}")
        return None

    def mute(self) -> None:
        # Save current volume before muting
        self._saved_volume = self._query_volume()
        if self._saved_volume is not None:
            log("audio_ctrl", f"Saved ADB volume: {self._saved_volume}")

        result = self._run_adb("shell", "cmd", "media_session", "volume", "--set", "0", "--stream", "3")
        if result is not None:
            log("audio_ctrl", f"Muted: {self.name} (ADB)")

    def unmute(self) -> None:
        vol = self._saved_volume if self._saved_volume is not None else self._unmute_volume
        result = self._run_adb("shell", "cmd", "media_session", "volume", "--set", str(vol), "--stream", "3")
        if result is not None:
            log("audio_ctrl", f"Unmuted: {self.name} (ADB, volume={vol})")


class ChromecastDevice:
    """Mute/unmute a Chromecast device on the local network."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._cast = None

    def _get_cast(self):
        if self._cast is not None:
            return self._cast
        try:
            import pychromecast
            chromecasts, _browser = pychromecast.get_listed_chromecasts(
                friendly_names=[self.name],
                discovery_timeout=5,
            )
            if chromecasts:
                self._cast = chromecasts[0]
                self._cast.wait()
                return self._cast
        except Exception as exc:
            log("audio_ctrl", f"Chromecast discovery failed for '{self.name}': {exc}")
        return None

    def mute(self) -> None:
        cast = self._get_cast()
        if cast:
            try:
                cast.set_volume_muted(True)
                log("audio_ctrl", f"Muted: {self.name} (Chromecast)")
            except Exception as exc:
                log("audio_ctrl", f"Mute failed for {self.name}: {exc}")

    def unmute(self) -> None:
        cast = self._get_cast()
        if cast:
            try:
                cast.set_volume_muted(False)
                log("audio_ctrl", f"Unmuted: {self.name} (Chromecast)")
            except Exception as exc:
                log("audio_ctrl", f"Unmute failed for {self.name}: {exc}")


class UpnpDevice:
    """Mute/unmute a UPnP/DLNA device on the local network."""

    def __init__(self, name: str, location: str = "") -> None:
        self.name = name
        self._location = location

    def mute(self) -> None:
        try:
            self._set_mute(True)
            log("audio_ctrl", f"Muted: {self.name} (UPnP)")
        except Exception as exc:
            log("audio_ctrl", f"Mute failed for {self.name}: {exc}")

    def unmute(self) -> None:
        try:
            self._set_mute(False)
            log("audio_ctrl", f"Unmuted: {self.name} (UPnP)")
        except Exception as exc:
            log("audio_ctrl", f"Unmute failed for {self.name}: {exc}")

    def _set_mute(self, muted: bool) -> None:
        import asyncio
        from async_upnp_client.aiohttp import AiohttpRequester
        from async_upnp_client.client import UpnpDevice as UpnpClientDevice
        from async_upnp_client.client_factory import UpnpFactory

        async def _do_mute():
            requester = AiohttpRequester()
            factory = UpnpFactory(requester)
            device = await factory.async_create_device(self._location)
            rc = device.service("urn:schemas-upnp-org:service:RenderingControl:1")
            if rc is None:
                log("audio_ctrl", f"No RenderingControl service on {self.name}")
                return
            action = rc.action("SetMute")
            await action.async_call(
                InstanceID=0,
                Channel="Master",
                DesiredMute=muted,
            )

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_do_mute())
        finally:
            loop.close()


@dataclass
class AudioControlConfig:
    enabled: bool = False
    mute_local: bool = True
    devices: list[dict] = field(default_factory=list)


class AudioController:
    """Manages muting/unmuting of all configured audio devices."""

    def __init__(self, config: AudioControlConfig) -> None:
        self._enabled = config.enabled
        self._devices: list[AudioDevice] = []

        if not config.enabled:
            return

        if config.mute_local:
            self._devices.append(LocalMacDevice())

        for dev_cfg in config.devices:
            dev_type = dev_cfg.get("type", "")
            dev_name = dev_cfg.get("name", "Unknown")

            if dev_type == "adb":
                serial = dev_cfg.get("serial", "")
                unmute_vol = int(dev_cfg.get("unmute_volume", 10))
                self._devices.append(AdbDevice(dev_name, serial, unmute_vol))
            elif dev_type == "chromecast":
                self._devices.append(ChromecastDevice(dev_name))
            elif dev_type == "upnp":
                location = dev_cfg.get("location", "")
                self._devices.append(UpnpDevice(dev_name, location))
            elif dev_type == "custom":
                mute_cmd = dev_cfg.get("mute_command", "")
                unmute_cmd = dev_cfg.get("unmute_command", "")
                if mute_cmd and unmute_cmd:
                    self._devices.append(CustomDevice(dev_name, mute_cmd, unmute_cmd))
                else:
                    log("audio_ctrl", f"Skipping custom device '{dev_name}': missing mute/unmute commands")
            else:
                log("audio_ctrl", f"Unknown device type '{dev_type}' for '{dev_name}'")

        if self._devices:
            names = ", ".join(d.name for d in self._devices)
            log("audio_ctrl", f"Configured {len(self._devices)} device(s): {names}")

    def mute(self) -> None:
        """Mute all configured devices. Non-blocking for network devices."""
        if not self._enabled or not self._devices:
            return

        local = [d for d in self._devices if isinstance(d, LocalMacDevice)]
        network = [d for d in self._devices if not isinstance(d, LocalMacDevice)]

        # Mute local Mac inline (fast, <50ms)
        for dev in local:
            try:
                dev.mute()
            except Exception as exc:
                log("audio_ctrl", f"Mute error: {exc}")

        # Mute network devices in background thread
        if network:
            threading.Thread(
                target=self._mute_network,
                args=(network,),
                daemon=True,
                name="audio-mute",
            ).start()

    def unmute(self) -> None:
        """Unmute all configured devices. Non-blocking for network devices."""
        if not self._enabled or not self._devices:
            return

        local = [d for d in self._devices if isinstance(d, LocalMacDevice)]
        network = [d for d in self._devices if not isinstance(d, LocalMacDevice)]

        for dev in local:
            try:
                dev.unmute()
            except Exception as exc:
                log("audio_ctrl", f"Unmute error: {exc}")

        if network:
            threading.Thread(
                target=self._unmute_network,
                args=(network,),
                daemon=True,
                name="audio-unmute",
            ).start()

    @staticmethod
    def _mute_network(devices: list[AudioDevice]) -> None:
        for dev in devices:
            try:
                dev.mute()
            except Exception as exc:
                log("audio_ctrl", f"Network mute error ({dev.name}): {exc}")

    @staticmethod
    def _unmute_network(devices: list[AudioDevice]) -> None:
        for dev in devices:
            try:
                dev.unmute()
            except Exception as exc:
                log("audio_ctrl", f"Network unmute error ({dev.name}): {exc}")


def _discover_all() -> list[dict]:
    """Discover all audio devices and return as list of dicts."""
    found: list[dict] = []

    # ADB devices
    for serial, model in _adb_devices():
        found.append({"type": "adb", "name": model, "serial": serial})

    # Chromecast
    try:
        import pychromecast
        chromecasts, browser = pychromecast.get_chromecasts(timeout=8)
        for cc in chromecasts:
            found.append({"type": "chromecast", "name": cc.name, "model": cc.model_name})
        pychromecast.discovery.stop_discovery(browser)
    except ImportError:
        pass
    except Exception:
        pass

    # UPnP/DLNA
    try:
        import asyncio
        from async_upnp_client.search import async_search

        async def _scan():
            results = []
            async def _cb(headers):
                location = headers.get("location", "")
                server = headers.get("server", "")
                st = headers.get("st", "")
                if "RenderingControl" in st or "MediaRenderer" in st:
                    results.append({"location": location, "server": server})
            await async_search(_cb, timeout=8)
            return results

        loop = asyncio.new_event_loop()
        try:
            for r in loop.run_until_complete(_scan()):
                found.append({"type": "upnp", "name": r["server"], "location": r["location"]})
        finally:
            loop.close()
    except ImportError:
        pass
    except Exception:
        pass

    return found


def _append_device_to_config(config_path, dev: dict) -> None:
    """Append a device entry to the [audio_control] section of config.toml."""
    from pathlib import Path
    path = Path(config_path)
    text = path.read_text(encoding="utf-8")

    dev_type = dev["type"]
    dev_name = dev["name"]

    block = f'\n[[audio_control.devices]]\ntype = "{dev_type}"\nname = "{dev_name}"\n'

    # Find the [audio_control] section and insert before the next section
    import re
    ac_match = re.search(r"(?m)^\[audio_control\]\s*$", text)
    if ac_match is None:
        # No [audio_control] section — append one
        text = text.rstrip() + "\n\n[audio_control]\nenabled = true\nmute_local = true\n" + block
    else:
        # Find the next section header after [audio_control]
        next_section = re.search(r"(?m)^\[[^\]]+\]\s*$", text[ac_match.end():])
        if next_section:
            insert_at = ac_match.end() + next_section.start()
            text = text[:insert_at] + block + "\n" + text[insert_at:]
        else:
            text = text.rstrip() + block

    path.write_text(text, encoding="utf-8")


def discover(config_path=None) -> None:
    """Discover audio devices and optionally add them to config."""
    print("\nScanning for audio devices...\n")

    found = _discover_all()

    if not found:
        print("No devices found.\n")
        # Print hints
        try:
            subprocess.run(["adb", "version"], capture_output=True, timeout=3)
            print("ADB is installed but no Android devices connected.")
            print("Pair via: Settings > Developer Options > Wireless debugging")
        except FileNotFoundError:
            print("For Android: install adb (brew install android-platform-tools)")
        print()
        return

    print(f"Found {len(found)} device(s):\n")
    for i, dev in enumerate(found, 1):
        print(f"  {i}. [{dev['type']}] {dev['name']}")
    print()

    if config_path is None:
        print("Run with --config to auto-add devices to your config.")
        return

    try:
        answer = input("Add all discovered devices to config? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if answer in ("", "y", "yes"):
        # Read existing config to skip duplicates
        existing = set()
        try:
            import tomllib
            with open(config_path, "rb") as f:
                cfg = tomllib.load(f)
            for d in cfg.get("audio_control", {}).get("devices", []):
                existing.add((d.get("type", ""), d.get("name", "")))
        except Exception:
            pass

        added = 0
        for dev in found:
            key = (dev["type"], dev["name"])
            if key in existing:
                print(f"  Skipped (already in config): [{dev['type']}] {dev['name']}")
                continue
            _append_device_to_config(config_path, dev)
            print(f"  Added: [{dev['type']}] {dev['name']}")
            added += 1

        if added:
            print(f"\nDone. {added} device(s) added to config.")
            print("Restart whisper-dic to pick up the changes.")
        else:
            print("\nAll discovered devices already in config.")
    else:
        print("No changes made.")
