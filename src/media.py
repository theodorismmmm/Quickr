"""Windows media session + toast helpers for Isle (winsdk).

Uses GlobalSystemMediaTransportControlsSessionManager so Spotify,
YouTube Music, and browser players appear without per-app scraping.
Toast polling uses UserNotificationListener only after access is Allowed.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("isle.media")

# PlaybackStatus.PLAYING == 4 in Windows.Media.Control
_PLAYING = 4

# Position for try_change_playback_position_async is in 100-ns ticks.
_TICKS_PER_SECOND = 10_000_000


@dataclass
class MediaInfo:
    """Snapshot of the current system media session."""

    active: bool = False
    playing: bool = False
    title: str = ""
    artist: str = ""
    source: str = ""
    position: float = 0.0
    duration: float = 0.0
    thumbnail: bytes = field(default_factory=bytes)
    can_play_pause: bool = False
    can_skip_next: bool = False
    can_skip_previous: bool = False
    can_seek: bool = False


@dataclass
class ToastInfo:
    """A toast notification shown in the island."""

    id: int
    app: str = ""
    title: str = ""
    body: str = ""

    @property
    def is_whatsapp(self) -> bool:
        return "whatsapp" in (self.app or "").lower()


def _friendly_source(app_id: Optional[str]) -> str:
    if not app_id:
        return "Media"
    lower = app_id.lower()
    mapping = (
        ("spotify", "Spotify"),
        ("youtubemusic", "YouTube Music"),
        ("youtube.music", "YouTube Music"),
        ("music.youtube", "YouTube Music"),
        ("youtube", "YouTube"),
        ("chrome", "Chrome"),
        ("msedge", "Edge"),
        ("firefox", "Firefox"),
        ("brave", "Brave"),
        ("vlc", "VLC"),
        ("itunes", "iTunes"),
        ("applemusic", "Apple Music"),
        ("amazon music", "Amazon Music"),
        ("amazonmusic", "Amazon Music"),
        ("tidal", "TIDAL"),
        ("foobar2000", "foobar2000"),
        ("aimp", "AIMP"),
        ("groove", "Groove"),
        ("media player", "Media Player"),
    )
    for needle, label in mapping:
        if needle in lower:
            return label
    # AUMID often looks like Package_xxx!App or App.exe
    base = app_id.split("!")[-1]
    base = base.rsplit("\\", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base or "Media"


def _is_youtube_music(app_id: Optional[str]) -> bool:
    if not app_id:
        return False
    lower = app_id.lower()
    return any(
        token in lower
        for token in ("youtubemusic", "youtube.music", "music.youtube", "youtube music")
    )


def _timedelta_seconds(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value.total_seconds())
    except Exception:
        try:
            return float(value.duration) / 10_000_000.0
        except Exception:
            return 0.0


class MediaService:
    """Background winsdk media + toast poller with thread-safe callbacks."""

    def __init__(
        self,
        on_media: Optional[Callable[[MediaInfo], None]] = None,
        on_toast: Optional[Callable[[ToastInfo], None]] = None,
        media_interval: float = 0.4,
        toast_interval: float = 1.5,
        settings: Optional[dict] = None,
    ) -> None:
        self._on_media = on_media
        self._on_toast = on_toast
        self._media_interval = media_interval
        self._toast_interval = toast_interval
        self._settings = dict(settings or {})

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()

        self._manager = None
        self._session = None
        self._last_thumb_key: Optional[str] = None
        self._thumbnail: bytes = b""
        self._seen_toast_ids: set[int] = set()
        self._toasts_enabled = False
        self._last_info = MediaInfo()

    def apply_settings(self, settings: dict) -> None:
        self._settings = dict(settings or {})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="isle-media",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(lambda: None)
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _run_loop(self) -> None:
        try:
            import winsdk  # noqa: F401
        except ImportError:
            log.warning("winsdk not available; media/toast features disabled")
            idle = MediaInfo()
            if self._on_media:
                self._on_media(idle)
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main())
        except Exception:
            log.exception("media service crashed")
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

    async def _main(self) -> None:
        await self._init_manager()
        await self._init_toasts()
        next_toast = 0.0
        while not self._stop.is_set():
            try:
                await self._poll_media()
            except Exception:
                log.exception("media poll failed")
            now = time.monotonic()
            if self._toasts_enabled and now >= next_toast:
                try:
                    await self._poll_toasts()
                except Exception:
                    log.exception("toast poll failed")
                next_toast = now + self._toast_interval
            await asyncio.sleep(self._media_interval)

    async def _init_manager(self) -> None:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        )

        try:
            self._manager = await MediaManager.request_async()
        except Exception:
            log.exception("failed to request media session manager")
            self._manager = None

    async def _init_toasts(self) -> None:
        """Enable toast polling only when request_access_async returns Allowed."""
        try:
            from winsdk.windows.ui.notifications.management import (
                UserNotificationListener,
                UserNotificationListenerAccessStatus,
            )
        except Exception:
            log.info("UserNotificationListener unavailable")
            return

        try:
            listener = UserNotificationListener.current
            access = await listener.request_access_async()
            allowed = UserNotificationListenerAccessStatus.ALLOWED
            # Some winsdk builds expose the enum member as an int-compatible value.
            if access == allowed or getattr(access, "name", "") == "ALLOWED":
                self._toasts_enabled = True
                log.info("toast listener access Allowed")
            else:
                log.info("toast listener access not Allowed (%s); skipping polls", access)
        except Exception:
            log.exception("toast access request failed")

    # ------------------------------------------------------------------
    # Media polling / controls
    # ------------------------------------------------------------------

    def _pick_session(self, manager):
        """Choose the active session, optionally preferring YouTube Music."""
        current = manager.get_current_session()
        try:
            sessions = list(manager.get_sessions() or [])
        except Exception:
            sessions = [current] if current is not None else []

        prefer_ytm = bool(self._settings.get("youtube_music_prefer", True))
        ytm_enabled = bool(self._settings.get("youtube_music_enabled", True))

        ytm_sessions = [
            s for s in sessions if s is not None and _is_youtube_music(s.source_app_user_model_id)
        ]

        if prefer_ytm and ytm_enabled and ytm_sessions:
            # Prefer a playing YTM session, else first YTM session.
            for s in ytm_sessions:
                try:
                    pb = s.get_playback_info()
                    if pb is not None and int(pb.playback_status) == _PLAYING:
                        return s
                except Exception:
                    continue
            return ytm_sessions[0]

        if current is not None and _is_youtube_music(current.source_app_user_model_id):
            if not ytm_enabled:
                # Skip YTM — fall back to another session if any.
                for s in sessions:
                    if s is not None and not _is_youtube_music(s.source_app_user_model_id):
                        return s
                return None
        return current

    async def _poll_media(self) -> None:
        info = MediaInfo()
        manager = self._manager
        if manager is None:
            self._emit_media(info)
            return

        session = self._pick_session(manager)
        self._session = session
        if session is None:
            self._last_thumb_key = None
            self._thumbnail = b""
            self._emit_media(info)
            return

        props = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()

        title = ""
        artist = ""
        if props is not None:
            title = (props.title or "").strip()
            artist = (props.artist or "").strip()
            thumb_key = f"{title}|{artist}|{session.source_app_user_model_id}"
            if props.thumbnail is not None and thumb_key != self._last_thumb_key:
                data = await self._read_thumbnail(props.thumbnail)
                if data:
                    self._thumbnail = data
                    self._last_thumb_key = thumb_key
            elif props.thumbnail is None:
                self._thumbnail = b""
                self._last_thumb_key = thumb_key

        playing = False
        can_play_pause = can_next = can_prev = can_seek = False
        if playback is not None:
            try:
                playing = int(playback.playback_status) == _PLAYING
            except Exception:
                playing = str(getattr(playback.playback_status, "name", "")).upper() == "PLAYING"
            controls = playback.controls
            if controls is not None:
                can_play_pause = bool(controls.is_play_pause_toggle_enabled)
                can_next = bool(controls.is_next_enabled)
                can_prev = bool(controls.is_previous_enabled)
                can_seek = bool(controls.is_playback_position_enabled)

        position = duration = 0.0
        if timeline is not None:
            position = _timedelta_seconds(timeline.position)
            duration = _timedelta_seconds(timeline.end_time)
            # When playing, advance from last_updated_time for smoother UI.
            if playing:
                try:
                    last = timeline.last_updated_time.timestamp()
                    rate = float(playback.playback_rate or 1.0) if playback else 1.0
                    position += max(0.0, time.time() - last) * rate
                    if duration > 0:
                        position = min(position, duration)
                except Exception:
                    pass

        active = bool(title or artist or playing or self._thumbnail)
        info = MediaInfo(
            active=active,
            playing=playing,
            title=title or "Unknown",
            artist=artist,
            source=_friendly_source(session.source_app_user_model_id),
            position=position,
            duration=duration,
            thumbnail=self._thumbnail,
            can_play_pause=can_play_pause,
            can_skip_next=can_next,
            can_skip_previous=can_prev,
            can_seek=can_seek,
        )
        self._emit_media(info)

    async def _read_thumbnail(self, stream_ref) -> bytes:
        """Read album art through the session thumbnail stream."""
        from winsdk.windows.storage.streams import Buffer, InputStreamOptions

        try:
            stream = await stream_ref.open_read_async()
        except Exception:
            log.debug("thumbnail open_read_async failed", exc_info=True)
            return b""
        try:
            size = int(stream.size or 0)
            if size <= 0:
                size = 512 * 1024
            buffer = Buffer(size)
            await stream.read_async(buffer, buffer.capacity, InputStreamOptions.READ_AHEAD)
            return bytes(bytearray(buffer))
        except Exception:
            log.debug("thumbnail read failed", exc_info=True)
            return b""
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _emit_media(self, info: MediaInfo) -> None:
        self._last_info = info
        if self._on_media:
            try:
                self._on_media(info)
            except Exception:
                log.exception("on_media callback failed")

    def _submit(self, coro) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(coro, loop)

    def toggle_play_pause(self) -> None:
        self._submit(self._toggle_play_pause())

    def skip_next(self) -> None:
        self._submit(self._skip_next())

    def skip_previous(self) -> None:
        self._submit(self._skip_previous())

    def seek(self, position_seconds: float) -> None:
        self._submit(self._seek(position_seconds))

    async def _toggle_play_pause(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            await session.try_toggle_play_pause_async()
        except Exception:
            log.exception("try_toggle_play_pause_async failed")

    async def _skip_next(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            await session.try_skip_next_async()
        except Exception:
            log.exception("try_skip_next_async failed")

    async def _skip_previous(self) -> None:
        session = self._session
        if session is None:
            return
        try:
            await session.try_skip_previous_async()
        except Exception:
            log.exception("try_skip_previous_async failed")

    async def _seek(self, position_seconds: float) -> None:
        session = self._session
        if session is None:
            return
        ticks = int(max(0.0, position_seconds) * _TICKS_PER_SECOND)
        try:
            await session.try_change_playback_position_async(ticks)
        except Exception:
            log.exception("try_change_playback_position_async failed")

    # ------------------------------------------------------------------
    # Toasts
    # ------------------------------------------------------------------

    async def _poll_toasts(self) -> None:
        from winsdk.windows.ui.notifications import (
            KnownNotificationBindings,
            NotificationKinds,
        )
        from winsdk.windows.ui.notifications.management import UserNotificationListener

        listener = UserNotificationListener.current
        notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
        if notifs is None:
            return

        current_ids: set[int] = set()
        # Iterate newest-first when possible
        items = list(notifs)
        for n in items:
            try:
                nid = int(n.id)
            except Exception:
                continue
            current_ids.add(nid)
            if nid in self._seen_toast_ids:
                continue
            toast = self._parse_toast(n, KnownNotificationBindings)
            if toast is None:
                continue
            if toast.is_whatsapp and not bool(
                self._settings.get("whatsapp_toasts_enabled", True)
            ):
                continue
            self._seen_toast_ids.add(nid)
            if self._on_toast:
                try:
                    self._on_toast(toast)
                except Exception:
                    log.exception("on_toast callback failed")

        # Drop ids that disappeared so re-shown toasts can appear again later
        if current_ids:
            self._seen_toast_ids &= current_ids

    def _parse_toast(self, notification, KnownNotificationBindings) -> Optional[ToastInfo]:
        app = ""
        try:
            app_info = notification.app_info
            if app_info is not None:
                app = app_info.display_info.display_name or ""
        except Exception:
            app = ""

        title = ""
        body_parts: list[str] = []
        try:
            visual = notification.notification.visual
            binding = visual.get_binding(KnownNotificationBindings.toast_generic)
            if binding is None:
                binding = visual.get_binding(KnownNotificationBindings.get_toast_generic())
            if binding is not None:
                texts = binding.get_text_elements()
                for i, el in enumerate(texts):
                    text = (el.text or "").strip()
                    if not text:
                        continue
                    if i == 0 and not title:
                        title = text
                    else:
                        body_parts.append(text)
        except Exception:
            log.debug("toast parse failed", exc_info=True)

        if not (app or title or body_parts):
            return None
        return ToastInfo(
            id=int(notification.id),
            app=app,
            title=title,
            body="\n".join(body_parts),
        )
