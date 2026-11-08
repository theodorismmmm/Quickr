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

_BT_AEP_SELECTOR = (
    'System.Devices.Aep.ProtocolId:="{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}"'
)
_AEP_PROPS = (
    "System.Devices.Aep.IsPresent",
    "System.Devices.Aep.IsConnected",
    "System.Devices.Aep.IsPaired",
    "System.Devices.Aep.DeviceAddress",
)


@dataclass
class BtDevice:
    name: str
    address: str
    is_iphone: bool = False
    is_paired: bool = False
    is_present: bool = False
    is_connected: bool = False


def _looks_like_iphone(name: str) -> bool:
    n = (name or "").lower()
    return any(tok in n for tok in ("iphone", "ipad", "ipod"))


def _prop_bool(properties, key: str) -> bool:
    if properties is None:
        return False
    try:
        if hasattr(properties, "has_key") and properties.has_key(key):
            return bool(properties.lookup(key))
        if hasattr(properties, "__contains__") and key in properties:
            return bool(properties[key])
    except Exception:
        return False
    return False


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
        self._wake: Optional[asyncio.Event] = None
        self._scan_task: Optional[asyncio.Task] = None
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
        """Signal the worker to exit without blocking the GUI thread.

        AEP FindAllAsync can take many seconds; joining here from Setup/close
        would freeze the UI. The worker is daemonized and checks _stop / cancels
        the in-flight scan instead.
        """
        self._stop.set()
        loop = self._loop
        if loop is not None and loop.is_running():
            def _wake_and_cancel() -> None:
                if self._wake is not None:
                    self._wake.set()
                task = self._scan_task
                if task is not None and not task.done():
                    task.cancel()

            try:
                loop.call_soon_threadsafe(_wake_and_cancel)
            except RuntimeError:
                pass
        # Do not join() here — keep the thread ref so start() can see it is alive.

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
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            loop.close()
            self._loop = None
            self._wake = None

    async def _main(self) -> None:
        self._wake = asyncio.Event()
        self._emit_status("Bluetooth ready — scanning…")
        while not self._stop.is_set():
            self._scan_task = asyncio.create_task(self._scan_once())
            try:
                await self._scan_task
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("bt scan failed")
                self._emit_status("Bluetooth scan failed")
            finally:
                self._scan_task = None
            if self._stop.is_set():
                break
            # Interruptible wait so stop() can exit between scans quickly.
            assert self._wake is not None
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=8.0)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    async def _scan_once(self) -> None:
        from winsdk.windows.devices.bluetooth import BluetoothAdapter
        from winsdk.windows.devices.enumeration import (
            DeviceInformation,
            DeviceInformationKind,
        )

        adapter = await BluetoothAdapter.get_default_async()
        if adapter is None:
            self._emit_status("No Bluetooth adapter")
            self._connected = False
            return

        found = None
        # AEP selector must be paired with AssociationEndpoint kind — the
        # one-arg FindAllAsync defaults to DeviceInterface and returns nothing.
        try:
            found = await DeviceInformation.find_all_async(
                _BT_AEP_SELECTOR,
                list(_AEP_PROPS),
                DeviceInformationKind.ASSOCIATION_ENDPOINT,
            )
        except TypeError:
            # Older winsdk builds: kind-only overload.
            try:
                found = await DeviceInformation.find_all_async(
                    _BT_AEP_SELECTOR,
                    DeviceInformationKind.ASSOCIATION_ENDPOINT,
                )
            except Exception:
                log.debug("AEP kind enumeration failed", exc_info=True)
        except Exception:
            log.debug("AEP enumeration failed", exc_info=True)

        if found is None or getattr(found, "size", None) == 0:
            # Empty result is not an exception — try a broader Bluetooth query.
            try:
                found = await DeviceInformation.find_all_async(
                    "Bluetooth",
                    DeviceInformationKind.ASSOCIATION_ENDPOINT,
                )
            except Exception:
                try:
                    found = await DeviceInformation.find_all_async("Bluetooth")
                except Exception:
                    log.debug("Bluetooth fallback enumeration failed", exc_info=True)
                    found = None

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
                props = getattr(info, "properties", None)
                # AEP enumeration can include unpaired nearby devices — read
                # IsPaired explicitly instead of assuming every result is paired.
                paired = _prop_bool(props, "System.Devices.Aep.IsPaired")
                devices.append(
                    BtDevice(
                        name=name,
                        address=address,
                        is_iphone=_looks_like_iphone(name),
                        is_paired=paired,
                        is_present=_prop_bool(props, "System.Devices.Aep.IsPresent"),
                        is_connected=_prop_bool(props, "System.Devices.Aep.IsConnected"),
                    )
                )

        devices.sort(
            key=lambda d: (
                not d.is_iphone,
                not d.is_paired,
                not d.is_connected,
                d.name.lower(),
            )
        )
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
            # Live link requires a paired endpoint that is present or connected.
            # Unpaired nearby AEPs must not report as Linked.
            live = bool(
                match is not None
                and match.is_paired
                and (match.is_connected or match.is_present)
            )
            self._connected = live
            if match is None:
                self._emit_status("iPhone not in range / not paired in Windows")
            elif not match.is_paired:
                self._emit_status(
                    f"Seen but not paired in Windows: {match.name}"
                )
            elif live:
                state = "connected" if match.is_connected else "in range"
                self._emit_status(f"Linked ({state}): {match.name}")
            else:
                self._emit_status(f"Paired but not in range: {match.name}")
        else:
            self._connected = False
            iphones = [d for d in devices if d.is_iphone and d.is_paired]
            if iphones:
                self._emit_status(
                    f"Found {len(iphones)} paired Apple device(s) — pick one in Setup"
                )
            else:
                self._emit_status(
                    "Pair your iPhone in Windows Bluetooth settings, then select it in Setup"
                )
