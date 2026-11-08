"""PySide6 Dynamic Island window for Windows (Isle).

Frameless, always-on-top tool window at the top-center of the primary screen.
Idle / compact / expanded sizes with OutCubic size animation.
Layout matches iOS-style music Dynamic Island references.
"""

from __future__ import annotations

import logging
import sys
import webbrowser
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import isle_settings as cfg
from media import MediaInfo, MediaService, ToastInfo
from settings_ui import SettingsWindow

log = logging.getLogger("isle.island")

IDLE_SIZE = QSize(126, 37)
COMPACT_SIZE = QSize(214, 44)
EXPANDED_SIZE = QSize(420, 236)
ANIM_MS = 320
TOP_MARGIN = 10
FILL = QColor("#000000")
RIM = QColor(255, 255, 255, 210)
INNER = QColor(255, 255, 255, 40)
WHITE = QColor(255, 255, 255)
ACCENT_FALLBACK = QColor(220, 160, 190)  # soft pink like the reference art


class IslandMode(Enum):
    IDLE = auto()
    COMPACT = auto()
    EXPANDED = auto()
    TOAST = auto()


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _rounded_pixmap(src: QPixmap, size: int, radius: float) -> QPixmap:
    """Square cover with rounded corners (reference style)."""
    if src.isNull():
        out = QPixmap(size, size)
        out.fill(Qt.transparent)
        return out
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - size) // 2)
    y = max(0, (scaled.height() - size) // 2)
    cropped = scaled.copy(x, y, size, size)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, cropped)
    p.end()
    return out


def _accent_from_image(image: QImage) -> QColor:
    """Sample a vivid accent from album art for the equalizer bars."""
    if image.isNull():
        return QColor(ACCENT_FALLBACK)
    img = image.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    best = QColor(ACCENT_FALLBACK)
    best_score = -1.0
    step = 2
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            c = img.pixelColor(x, y)
            # Prefer saturated mid/high brightness pixels (skip near-black/white).
            h, s, v, _a = c.getHsvF()
            if s < 0.25 or v < 0.25 or v > 0.95:
                continue
            score = s * 1.4 + v * 0.4
            if score > best_score:
                best_score = score
                best = QColor.fromHsvF(h, min(1.0, s * 1.05), min(1.0, max(0.55, v)), 1.0)
    return best


class WaveBars(QWidget):
    """Compact/expanded equalizer bars — rounded, accent-tinted like the reference."""

    def __init__(self, parent: Optional[QWidget] = None, *, bar_count: int = 4) -> None:
        super().__init__(parent)
        self._count = bar_count
        self.setFixedSize(26 if bar_count <= 4 else 30, 18)
        self._levels = [0.35, 0.7, 0.45, 0.85, 0.55][:bar_count]
        self._playing = False
        self._phase = 0
        self._color = QColor(ACCENT_FALLBACK)
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)

    def set_accent(self, color: QColor) -> None:
        if color.isValid():
            self._color = QColor(color)
            self.update()

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        if playing:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._levels = [0.28] * self._count
            self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % 8
        patterns = (
            (0.30, 0.85, 0.45, 0.70, 0.55),
            (0.55, 0.40, 0.90, 0.35, 0.75),
            (0.75, 0.55, 0.30, 0.95, 0.40),
            (0.40, 0.95, 0.65, 0.45, 0.80),
            (0.65, 0.35, 0.80, 0.55, 0.30),
            (0.35, 0.70, 0.50, 0.85, 0.60),
            (0.85, 0.50, 0.35, 0.60, 0.90),
            (0.50, 0.65, 0.90, 0.40, 0.70),
        )
        self._levels = list(patterns[self._phase][: self._count])
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self._color))
        w = self.width()
        h = self.height()
        bar_w = 3.2
        gap = 2.6
        total = self._count * bar_w + (self._count - 1) * gap
        x0 = (w - total) / 2.0
        for i, level in enumerate(self._levels):
            bh = max(3.0, h * level)
            x = x0 + i * (bar_w + gap)
            y = h - bh
            p.drawRoundedRect(QRectF(x, y, bar_w, bh), 1.5, 1.5)
        p.end()


class IslandWindow(QWidget):
    """Top-center Dynamic Island chrome."""

    media_updated = Signal(object)
    toast_received = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("IsleWindow")
        self.setWindowTitle("Isle")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )

        self._mode = IslandMode.IDLE
        self._hover = False
        self._pinned = False
        self._media = MediaInfo()
        self._toast: Optional[ToastInfo] = None
        self._scrubbing = False
        self._radius = 18.0
        self._accent = QColor(ACCENT_FALLBACK)
        self._settings = cfg.load()
        self._settings_window: Optional[SettingsWindow] = None

        self._build_ui()
        self._wire_media()
        self._setup_tray()

        self._size_anim = QPropertyAnimation(self, b"size", self)
        self._size_anim.setDuration(ANIM_MS)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._size_anim.valueChanged.connect(self._on_size_anim)
        self._size_anim.finished.connect(self._recenter)

        self.media_updated.connect(self._apply_media)
        self.toast_received.connect(self._apply_toast)

        self.resize(IDLE_SIZE)
        self._show_mode_widgets()
        self._recenter()

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._dismiss_toast)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        # Compact: cover left · empty black · bars right (reference)
        self.compact = QWidget(self)
        compact_l = QHBoxLayout(self.compact)
        compact_l.setContentsMargins(0, 0, 0, 0)
        compact_l.setSpacing(0)
        self.compact_cover = QLabel(self.compact)
        self.compact_cover.setFixedSize(28, 28)
        self.compact_bars = WaveBars(self.compact, bar_count=4)
        compact_l.addWidget(self.compact_cover, 0, Qt.AlignVCenter)
        compact_l.addStretch(1)
        compact_l.addWidget(self.compact_bars, 0, Qt.AlignVCenter)
        root.addWidget(self.compact)

        # Expanded media panel (reference: art + meta + bars / times / scrub / controls)
        self.expanded = QWidget(self)
        exp = QVBoxLayout(self.expanded)
        exp.setContentsMargins(0, 0, 0, 0)
        exp.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.cover = QLabel(self.expanded)
        self.cover.setFixedSize(72, 72)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.setContentsMargins(0, 4, 0, 0)
        self.title_lbl = QLabel("Title", self.expanded)
        self.title_lbl.setStyleSheet(
            "color:#ffffff;font-size:15px;font-weight:600;letter-spacing:-0.2px;"
        )
        self.title_lbl.setWordWrap(True)
        self.artist_lbl = QLabel("Artist", self.expanded)
        self.artist_lbl.setStyleSheet("color:#9a9a9a;font-size:12px;")
        meta.addWidget(self.title_lbl)
        meta.addWidget(self.artist_lbl)
        meta.addStretch(1)
        self.expanded_bars = WaveBars(self.expanded, bar_count=5)
        top.addWidget(self.cover, 0, Qt.AlignTop)
        top.addLayout(meta, 1)
        top.addWidget(self.expanded_bars, 0, Qt.AlignTop)
        exp.addLayout(top)

        # Times sit above the scrubber (reference)
        times = QHBoxLayout()
        times.setContentsMargins(2, 0, 2, 0)
        self.elapsed_lbl = QLabel("0:00", self.expanded)
        self.elapsed_lbl.setStyleSheet("color:#d8d8d8;font-size:11px;")
        self.remaining_lbl = QLabel("-0:00", self.expanded)
        self.remaining_lbl.setStyleSheet("color:#d8d8d8;font-size:11px;")
        self.remaining_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        times.addWidget(self.elapsed_lbl)
        times.addStretch(1)
        times.addWidget(self.remaining_lbl)
        exp.addLayout(times)

        self.scrubber = QSlider(Qt.Horizontal, self.expanded)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setFixedHeight(14)
        # Filled = mid grey, track = darker grey (reference) — not bright white.
        self.scrubber.setStyleSheet(
            """
            QSlider::groove:horizontal {
                height: 4px;
                background: #2e2e2e;
                border: none;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #8a8a8a;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 0px;
                height: 0px;
                margin: 0;
                background: transparent;
                border: none;
            }
            QSlider::handle:horizontal:hover {
                width: 10px;
                height: 10px;
                margin: -3px 0;
                background: #ffffff;
                border-radius: 5px;
            }
            """
        )
        self.scrubber.sliderPressed.connect(self._on_scrub_press)
        self.scrubber.sliderReleased.connect(self._on_scrub_release)
        self.scrubber.sliderMoved.connect(self._on_scrub_moved)
        exp.addWidget(self.scrubber)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 4, 0, 0)
        controls.setSpacing(28)
        self.prev_btn = self._control_button("⏮", self._on_prev)
        self.play_btn = self._control_button("⏸", self._on_play_pause)
        self.next_btn = self._control_button("⏭", self._on_next)
        self.output_btn = self._control_button("📡", self._on_output)
        self.output_btn.setFixedSize(28, 28)
        self.output_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #b0b0b0; border: none;"
            " font-size: 13px; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        controls.addStretch(1)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addStretch(1)
        controls.addWidget(self.output_btn, 0, Qt.AlignRight | Qt.AlignVCenter)
        exp.addLayout(controls)
        root.addWidget(self.expanded)

        # Toast panel
        self.toast_panel = QWidget(self)
        toast_l = QVBoxLayout(self.toast_panel)
        toast_l.setContentsMargins(0, 0, 0, 0)
        toast_l.setSpacing(6)
        self.toast_app = QLabel("", self.toast_panel)
        self.toast_app.setStyleSheet("color:#8a8a8a;font-size:11px;")
        self.toast_title = QLabel("", self.toast_panel)
        self.toast_title.setStyleSheet("color:#ffffff;font-size:13px;font-weight:600;")
        self.toast_title.setWordWrap(True)
        self.toast_body = QLabel("", self.toast_panel)
        self.toast_body.setStyleSheet("color:#c8c8c8;font-size:12px;")
        self.toast_body.setWordWrap(True)
        toast_l.addWidget(self.toast_app)
        toast_l.addWidget(self.toast_title)
        toast_l.addWidget(self.toast_body)

        self.whatsapp_row = QWidget(self.toast_panel)
        wa = QHBoxLayout(self.whatsapp_row)
        wa.setContentsMargins(0, 4, 0, 0)
        wa.setSpacing(8)
        self.reply_edit = QLineEdit(self.whatsapp_row)
        self.reply_edit.setPlaceholderText("Reply (copies + opens WhatsApp)")
        self.reply_edit.setStyleSheet(
            "QLineEdit { background:#111; color:#fff; border:1px solid #333;"
            " padding:6px 8px; border-radius:6px; }"
        )
        self.reply_btn = QPushButton("Open", self.whatsapp_row)
        self.reply_btn.setCursor(Qt.PointingHandCursor)
        self.reply_btn.setStyleSheet(
            "QPushButton { background:#1a1a1a; color:#fff; border:1px solid #444;"
            " padding:6px 12px; border-radius:6px; }"
            "QPushButton:hover { border-color:#888; }"
        )
        self.reply_btn.clicked.connect(self._on_whatsapp_reply)
        self.reply_edit.returnPressed.connect(self._on_whatsapp_reply)
        wa.addWidget(self.reply_edit, 1)
        wa.addWidget(self.reply_btn)
        self.whatsapp_row.hide()
        toast_l.addWidget(self.whatsapp_row)
        root.addWidget(self.toast_panel)

        font = QFont("Segoe UI", 10)
        self.setFont(font)

    def _control_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text, self.expanded)
        btn.setFixedSize(40, 40)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ffffff; border: none;"
            " font-size: 18px; }"
            "QPushButton:hover { color: #dddddd; }"
            "QPushButton:disabled { color: #555555; }"
        )
        btn.clicked.connect(slot)
        return btn

    def _wire_media(self) -> None:
        self._service = MediaService(
            on_media=lambda info: self.media_updated.emit(info),
            on_toast=lambda toast: self.toast_received.emit(toast),
            settings=self._settings,
        )
        self._service.start()

    def _setup_tray(self) -> None:
        pix = QPixmap(16, 16)
        pix.fill(FILL)
        self._tray = QSystemTrayIcon(QIcon(pix), self)
        self._tray.setToolTip("Isle")
        menu = QMenu()

        setup_action = QAction("Setup (YouTube Music / WhatsApp)…", menu)
        setup_action.triggered.connect(self.open_settings)
        menu.addAction(setup_action)

        yt_action = QAction("Open YouTube Music", menu)
        yt_action.triggered.connect(self._tray_open_youtube)
        menu.addAction(yt_action)

        wa_action = QAction("Open WhatsApp", menu)
        wa_action.triggered.connect(self._tray_open_whatsapp)
        menu.addAction(wa_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()

    def open_settings(self) -> None:
        if self._settings_window is None:
            self._settings_window = SettingsWindow(on_changed=self._on_settings_changed)
        self._settings_window.reload()
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_changed(self, data: dict) -> None:
        self._settings = dict(data)
        self._service.apply_settings(self._settings)

    def _tray_open_youtube(self) -> None:
        webbrowser.open(
            str(self._settings.get("youtube_music_url") or "https://music.youtube.com")
        )

    def _tray_open_whatsapp(self) -> None:
        webbrowser.open(str(self._settings.get("whatsapp_uri") or "whatsapp:"))

    # ------------------------------------------------------------------
    # Geometry / paint
    # ------------------------------------------------------------------

    def _target_size(self) -> QSize:
        if self._mode == IslandMode.EXPANDED:
            return QSize(EXPANDED_SIZE)
        if self._mode == IslandMode.COMPACT:
            return QSize(COMPACT_SIZE)
        if self._mode == IslandMode.TOAST:
            h = 120 if not (self._toast and self._toast.is_whatsapp) else 168
            return QSize(360, h)
        return QSize(IDLE_SIZE)

    def _radius_for(self, size: QSize) -> float:
        # Idle/compact = full pill; expanded/toast = large rounded rect (reference).
        if size.height() >= 100:
            return 42.0
        return min(size.width(), size.height()) / 2.0

    def _recenter(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + TOP_MARGIN
        self.move(x, y)

    def _on_size_anim(self, value) -> None:
        if isinstance(value, QSize):
            self._radius = self._radius_for(value)
        self._recenter()
        self.update()

    def _animate_to(self, size: QSize) -> None:
        if self.size() == size:
            self._radius = self._radius_for(size)
            self._recenter()
            return
        self._size_anim.stop()
        self._size_anim.setStartValue(self.size())
        self._size_anim.setEndValue(size)
        self._size_anim.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        r = self._radius_for(self.size())
        path.addRoundedRect(rect, r, r)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(FILL))
        p.drawPath(path)

        # Subtle resting rim on compact (as in the photo); stronger rim on hover.
        if self._mode == IslandMode.COMPACT and not self._hover:
            pen = QPen(QColor(255, 255, 255, 28))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        if self._hover or self._pinned or self._mode in (IslandMode.EXPANDED, IslandMode.TOAST):
            pen = QPen(RIM)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            inner = QRectF(self.rect()).adjusted(2.2, 2.2, -2.2, -2.2)
            inner_path = QPainterPath()
            inner_r = max(2.0, r - 2.0)
            inner_path.addRoundedRect(inner, inner_r, inner_r)
            ipen = QPen(INNER)
            ipen.setWidthF(1.0)
            p.setPen(ipen)
            p.drawPath(inner_path)

        p.end()

    # ------------------------------------------------------------------
    # Mode / content
    # ------------------------------------------------------------------

    def _show_mode_widgets(self) -> None:
        self.compact.setVisible(self._mode == IslandMode.COMPACT)
        self.expanded.setVisible(self._mode == IslandMode.EXPANDED)
        self.toast_panel.setVisible(self._mode == IslandMode.TOAST)
        margins = {
            IslandMode.IDLE: (0, 0, 0, 0),
            IslandMode.COMPACT: (10, 8, 12, 8),
            IslandMode.EXPANDED: (20, 18, 20, 16),
            IslandMode.TOAST: (16, 14, 16, 14),
        }[self._mode]
        self.layout().setContentsMargins(*margins)

    def _recompute_mode(self) -> None:
        if self._toast is not None and self._mode == IslandMode.TOAST:
            pass
        elif self._pinned or (self._hover and self._media.active):
            self._mode = IslandMode.EXPANDED if self._media.active else IslandMode.IDLE
        elif self._media.active:
            self._mode = IslandMode.COMPACT
        else:
            self._mode = IslandMode.IDLE
            self._pinned = False

        self._show_mode_widgets()
        self._animate_to(self._target_size())

    def _apply_media(self, info: MediaInfo) -> None:
        self._media = info
        self._update_media_widgets()
        if self._mode != IslandMode.TOAST:
            self._recompute_mode()

    def _update_media_widgets(self) -> None:
        info = self._media
        image = QImage.fromData(info.thumbnail) if info.thumbnail else QImage()
        if not image.isNull():
            self._accent = _accent_from_image(image)
        else:
            self._accent = QColor(ACCENT_FALLBACK)

        if image.isNull():
            blank = QPixmap(72, 72)
            blank.fill(QColor("#1a1a1a"))
            cover_pix = _rounded_pixmap(blank, 72, 14)
            compact_pix = _rounded_pixmap(blank, 28, 8)
        else:
            full = QPixmap.fromImage(image)
            cover_pix = _rounded_pixmap(full, 72, 14)
            compact_pix = _rounded_pixmap(full, 28, 8)

        self.cover.setPixmap(cover_pix)
        self.compact_cover.setPixmap(compact_pix)
        self.compact_bars.set_accent(self._accent)
        self.compact_bars.set_playing(info.playing)
        self.expanded_bars.set_accent(self._accent)
        self.expanded_bars.set_playing(info.playing)

        self.title_lbl.setText(info.title or "Unknown")
        self.artist_lbl.setText(info.artist or "")
        self.play_btn.setText("⏸" if info.playing else "▶")
        self.prev_btn.setEnabled(info.can_skip_previous)
        self.next_btn.setEnabled(info.can_skip_next)
        self.play_btn.setEnabled(info.can_play_pause or info.active)
        self.scrubber.setEnabled(info.can_seek)

        if not self._scrubbing:
            duration = max(info.duration, 0.0)
            pos = max(0.0, min(info.position, duration if duration else info.position))
            self.elapsed_lbl.setText(_format_time(pos))
            remain = max(0.0, duration - pos) if duration else 0.0
            self.remaining_lbl.setText(f"-{_format_time(remain)}")
            if duration > 0:
                self.scrubber.setValue(int((pos / duration) * 1000))
            else:
                self.scrubber.setValue(0)

    def _apply_toast(self, toast: ToastInfo) -> None:
        if toast.is_whatsapp and not bool(self._settings.get("whatsapp_toasts_enabled", True)):
            return
        self._toast = toast
        self.toast_app.setText(toast.app or "Notification")
        self.toast_title.setText(toast.title or "")
        self.toast_body.setText(toast.body or "")
        show_reply = toast.is_whatsapp and bool(
            self._settings.get("whatsapp_reply_enabled", True)
        )
        if show_reply:
            self.whatsapp_row.show()
            self.reply_edit.clear()
        else:
            self.whatsapp_row.hide()
        self._mode = IslandMode.TOAST
        self._show_mode_widgets()
        self._animate_to(self._target_size())
        self._toast_timer.start(8000)

    def _dismiss_toast(self) -> None:
        self._toast = None
        self.whatsapp_row.hide()
        if self._mode == IslandMode.TOAST:
            self._recompute_mode()

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        if self._mode != IslandMode.TOAST and self._media.active:
            self._mode = IslandMode.EXPANDED
            self._show_mode_widgets()
            self._animate_to(self._target_size())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        if self._mode != IslandMode.TOAST and not self._pinned:
            self._mode = IslandMode.COMPACT if self._media.active else IslandMode.IDLE
            self._show_mode_widgets()
            self._animate_to(self._target_size())
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())
            interactive = (
                self.prev_btn,
                self.play_btn,
                self.next_btn,
                self.output_btn,
                self.scrubber,
                self.reply_edit,
                self.reply_btn,
            )
            on_control = child is not None and (
                child in interactive or self._is_descendant(child, interactive)
            )
            if not on_control and self._media.active:
                self._pinned = not self._pinned
                if self._pinned:
                    self._mode = IslandMode.EXPANDED
                elif not self._hover:
                    self._mode = IslandMode.COMPACT
                self._show_mode_widgets()
                self._animate_to(self._target_size())
                self.update()
        super().mousePressEvent(event)

    def _is_descendant(self, widget: Optional[QWidget], roots) -> bool:
        while widget is not None:
            if widget in roots:
                return True
            widget = widget.parentWidget()
        return False

    def _on_play_pause(self) -> None:
        self._service.toggle_play_pause()

    def _on_next(self) -> None:
        self._service.skip_next()

    def _on_prev(self) -> None:
        self._service.skip_previous()

    def _on_output(self) -> None:
        """Open Windows sound output settings (AirPlay-style control stand-in)."""
        if sys.platform == "win32":
            try:
                import os

                os.startfile("ms-settings:sound")  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        webbrowser.open("ms-settings:sound")

    def _on_scrub_press(self) -> None:
        self._scrubbing = True

    def _on_scrub_moved(self, value: int) -> None:
        duration = self._media.duration
        if duration <= 0:
            return
        pos = (value / 1000.0) * duration
        self.elapsed_lbl.setText(_format_time(pos))
        self.remaining_lbl.setText(f"-{_format_time(max(0.0, duration - pos))}")

    def _on_scrub_release(self) -> None:
        duration = self._media.duration
        value = self.scrubber.value()
        self._scrubbing = False
        if duration <= 0:
            return
        self._service.seek((value / 1000.0) * duration)

    def _on_whatsapp_reply(self) -> None:
        """Copy reply text and open the whatsapp: URI.

        This does NOT send the toast's inline reply action, and it does NOT
        automate WhatsApp Web — it only prepares the clipboard and launches
        the WhatsApp protocol handler.
        """
        if not bool(self._settings.get("whatsapp_reply_enabled", True)):
            return
        text = self.reply_edit.text().strip()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        webbrowser.open(str(self._settings.get("whatsapp_uri") or "whatsapp:"))
        self.reply_edit.clear()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._service.stop()
        except Exception:
            pass
        if hasattr(self, "_tray"):
            self._tray.hide()
        if self._settings_window is not None:
            self._settings_window.close()
        super().closeEvent(event)


class SingleInstance:
    """Ensure only one Isle process is running (QLocalServer)."""

    KEY = "IsleDynamicIslandSingleInstance"

    def __init__(self) -> None:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        self._QLocalServer = QLocalServer
        self._QLocalSocket = QLocalSocket
        self._server = None

    def acquire(self) -> bool:
        socket = self._QLocalSocket()
        socket.connectToServer(self.KEY)
        if socket.waitForConnected(150):
            socket.disconnectFromServer()
            return False
        self._QLocalServer.removeServer(self.KEY)
        self._server = self._QLocalServer()
        return bool(self._server.listen(self.KEY))

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._QLocalServer.removeServer(self.KEY)
            self._server = None


def run() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Isle")
    app.setOrganizationName("Quickr")

    guard = SingleInstance()
    if not guard.acquire():
        log.error("Isle is already running")
        return 1

    window = IslandWindow()
    window.show()

    code = app.exec()
    guard.release()
    return code
