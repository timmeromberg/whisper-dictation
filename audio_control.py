"""Auto-mute/unmute audio devices during recording."""

from __future__ import annotations

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

    def mute(self) -> None:
        subprocess.run(
            ["osascript", "-e", "set volume output muted true"],
            capture_output=True, timeout=5,
        )
        log("audio_ctrl", "Muted: Local Mac")

    def unmute(self) -> None:
        subprocess.run(
            ["osascript", "-e", "set volume output muted false"],
            capture_output=True, timeout=5,
        )
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

            if dev_type == "chromecast":
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


def discover() -> None:
    """Discover audio devices on the local network and print results."""
    print("\nScanning for audio devices on the local network...\n")

    # Chromecast discovery
    print("--- Chromecast devices ---")
    try:
        import pychromecast
        chromecasts, browser = pychromecast.get_chromecasts(timeout=8)
        if chromecasts:
            for cc in chromecasts:
                print(f"  Name: {cc.name}")
                print(f"  Type: chromecast")
                print(f"  Model: {cc.model_name}")
                print()
        else:
            print("  (none found)")
        pychromecast.discovery.stop_discovery(browser)
    except ImportError:
        print("  pychromecast not installed. Run: pip install pychromecast")
    except Exception as exc:
        print(f"  Discovery error: {exc}")

    print()

    # UPnP/DLNA discovery
    print("--- UPnP/DLNA devices ---")
    try:
        import asyncio
        from async_upnp_client.search import async_search

        async def _scan():
            found = []
            async def _cb(headers):
                location = headers.get("location", "")
                server = headers.get("server", "")
                st = headers.get("st", "")
                if "RenderingControl" in st or "MediaRenderer" in st:
                    found.append({"location": location, "server": server, "st": st})

            await async_search(_cb, timeout=8)
            return found

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(_scan())
        finally:
            loop.close()

        if results:
            for r in results:
                print(f"  Location: {r['location']}")
                print(f"  Server: {r['server']}")
                print(f"  Type: upnp")
                print()
        else:
            print("  (none found)")
    except ImportError:
        print("  async-upnp-client not installed. Run: pip install async-upnp-client")
    except Exception as exc:
        print(f"  Discovery error: {exc}")

    print()
    print("Add discovered devices to your config.toml [audio_control] section.")
    print("See config.example.toml for examples.")
