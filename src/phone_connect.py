"""iPhone Connect — Bluetooth device discovery for Isle.

Apple Continuity notification mirroring is not available to third-party
Windows apps. This module pairs/selects a phone over Bluetooth and keeps
connection status for the island UI. Notifications still come from the
Windows UserNotificationListener (WhatsApp, Phone Link, browsers, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

log = logging.getLogger("isle.phone")


@dataclass
class BtDevice:
    name: str
    address: str
    is_iphone: bool = False
    is_paired: bool = False


def _looks_like_iphone(name: str) -> bool:
    n = (name or "").lower()
    return any(tok in n for tok in ("iphone", "ipad", "ipod"))


class PhoneConnectService:
    """Background Bluetooth watcher (winsdk) for iPhone Connect."""

    def __init__(
        self,
        on_devices: Optional[Callable[[List[BtDevice]], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_devices = on_devices
        self._on_status = on_status
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()
        self._target_address: str = ""
        self._connected = False
        self._devices: List[BtDevice] = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def devices(self) -> List[BtDevice]:
        return list(self._devices)

    def set_target(self, address: str) -> None:
        self._target_address = (address or "").strip()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="isle-bt", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def refresh(self) -> None:
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._scan_once(), loop)

    def _emit_status(self, text: str) -> None:
        if self._on_status:
            try:
                self._on_status(text)
            except Exception:
                log.exception("on_status failed")

    def _emit_devices(self, devices: List[BtDevice]) -> None:
        self._devices = devices
        if self._on_devices:
            try:
                self._on_devices(devices)
            except Exception:
                log.exception("on_devices failed")

    def _run(self) -> None:
        try:
            import winsdk  # noqa: F401
        except ImportError:
            self._emit_status("Bluetooth APIs unavailable (winsdk missing)")
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        except Exception:
            log.exception("phone connect crashed")
        finally:
            loop.close()
            self._loop = None

    async def _main(self) -> None:
        self._emit_status("Bluetooth ready — scanning…")
        while not self._stop.is_set():
            try:
                await self._scan_once()
            except Exception:
                log.exception("bt scan failed")
                self._emit_status("Bluetooth scan failed")
            await asyncio.sleep(8.0)

    async def _scan_once(self) -> None:
        from winsdk.windows.devices.bluetooth import BluetoothAdapter
        from winsdk.windows.devices.enumeration import DeviceInformation

        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None:
            self._emit_status("No Bluetooth adapter")
            self._connected = False
            return

        # AQS selector for Bluetooth devices (paired + LE).
        selector = (
            "System.Devices.Aep.ProtocolId:=\"{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}\""
        )
        try:
            found = await DeviceInformation.find_all_async(selector)
        except Exception:
            # Fallback: device selector string for Bluetooth
            found = await DeviceInformation.find_all_async("Bluetooth")

        devices: List[BtDevice] = []
        seen = set()
        if found is not None:
            for info in found:
                name = (info.name or "").strip() or "Unknown"
                address = info.id or ""
                key = address.lower()
                if key in seen:
                    continue
                seen.add(key)
                devices.append(
                    BtDevice(
                        name=name,
                        address=address,
                        is_iphone=_looks_like_iphone(name),
                        is_paired=True,
                    )
                )

        # Prefer iPhones first in the list.
        devices.sort(key=lambda d: (not d.is_iphone, d.name.lower()))
        self._emit_devices(devices)

        if self._target_address:
            match = next(
                (
                    d
                    for d in devices
                    if d.address == self._target_address
                    or self._target_address.lower() in d.address.lower()
                    or self._target_address.lower() in d.name.lower()
                ),
                None,
            )
            self._connected = match is not None
            if match:
                self._emit_status(f"Linked: {match.name}")
            else:
                self._emit_status("iPhone not in range / not paired in Windows")
        else:
            self._connected = False
            iphones = [d for d in devices if d.is_iphone]
            if iphones:
                self._emit_status(f"Found {len(iphones)} Apple device(s) — pick one in Setup")
            else:
                self._emit_status(
                    "Pair your iPhone in Windows Bluetooth settings, then select it in Setup"
                )
