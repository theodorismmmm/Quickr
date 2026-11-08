"""PySide6 Dynamic Island for Windows (Isle) — always on top over apps.

Hover to expand, leave or click away to collapse. Style presets include
Liquid Glass, Apple, Xiaomi, Samsung Dot, and Notch. Includes timer and
iPhone Connect (Bluetooth link + Windows notifications across apps).
"""

from __future__ import annotations

import logging
import sys
import time
import webbrowser
from enum import Enum, auto
from typing import List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
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
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QImage,
    QLinearGradient,
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
from isle_styles import IsleStyle, get_style
from media import MediaInfo, MediaService, ToastInfo
from phone_connect import BtDevice, PhoneConnectService
from settings_ui import SettingsWindow

log = logging.getLogger("isle.island")

ANIM_MS = 320
WHITE = QColor(255, 255, 255)
MUTED = QColor(180, 180, 180)
ACCENT_FALLBACK = QColor(210, 145, 175)


class IslandMode(Enum):
    IDLE = auto()
    COMPACT = auto()
    EXPANDED = auto()
    TOAST = auto()
    TIMER = auto()


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _rounded_pixmap(src: QPixmap, size: int, radius: float) -> QPixmap:
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
    if image.isNull():
        return QColor(ACCENT_FALLBACK)
    img = image.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    best = QColor(ACCENT_FALLBACK)
    best_score = -1.0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixelColor(x, y)
            h, s, v, _a = c.getHsvF()
            if s < 0.22 or v < 0.22 or v > 0.95:
                continue
            score = s * 1.4 + v * 0.4
            if score > best_score:
                best_score = score
                best = QColor.fromHsvF(h, min(1.0, s * 1.05), min(1.0, max(0.55, v)), 1.0)
    return best


class IconButton(QWidget):
    clicked = Signal()

    def __init__(self, kind: str, parent: Optional[QWidget] = None, *, size: int = 40) -> None:
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self._enabled = True
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.update()
        super().setEnabled(enabled)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.LeftButton
            and self._enabled
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._enabled:
            color = QColor(70, 70, 70)
        elif self._hover:
            color = QColor(235, 235, 235)
        elif self._kind == "airplay":
            color = QColor(MUTED)
        else:
            color = QColor(WHITE)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        if self._kind == "prev":
            self._draw_skip(p, cx, cy, left=True)
        elif self._kind == "next":
            self._draw_skip(p, cx, cy, left=False)
        elif self._kind == "pause":
            w, h, gap = 4.5, 16.0, 5.0
            p.drawRoundedRect(QRectF(cx - gap / 2 - w, cy - h / 2, w, h), 1.2, 1.2)
            p.drawRoundedRect(QRectF(cx + gap / 2, cy - h / 2, w, h), 1.2, 1.2)
        elif self._kind == "play":
            path = QPainterPath()
            path.moveTo(cx - 5.5, cy - 9)
            path.lineTo(cx - 5.5, cy + 9)
            path.lineTo(cx + 9.5, cy)
            path.closeSubpath()
            p.drawPath(path)
        elif self._kind == "airplay":
            pen = QPen(color)
            pen.setWidthF(1.6)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            for r in (5.5, 9.0):
                p.drawArc(QRectF(cx - r, cy - r - 2, r * 2, r * 2), 40 * 16, 100 * 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(color))
            tri = QPainterPath()
            tri.moveTo(cx, cy + 2)
            tri.lineTo(cx - 6, cy + 10)
            tri.lineTo(cx + 6, cy + 10)
            tri.closeSubpath()
            p.drawPath(tri)
        p.end()

    def _draw_skip(self, p: QPainter, cx: float, cy: float, *, left: bool) -> None:
        sign = -1.0 if left else 1.0
        bar_w, bar_h = 2.4, 15.0
        tri_w, tri_h = 8.5, 15.0
        bar_x = cx + sign * 9.0 - (bar_w if sign > 0 else 0)
        p.drawRoundedRect(QRectF(bar_x, cy - bar_h / 2, bar_w, bar_h), 0.8, 0.8)
        for offset in (-3.2, 4.2):
            ox = cx + sign * offset
            path = QPainterPath()
            if left:
                path.moveTo(ox + tri_w / 2, cy - tri_h / 2)
                path.lineTo(ox - tri_w / 2, cy)
                path.lineTo(ox + tri_w / 2, cy + tri_h / 2)
            else:
                path.moveTo(ox - tri_w / 2, cy - tri_h / 2)
                path.lineTo(ox + tri_w / 2, cy)
                path.lineTo(ox - tri_w / 2, cy + tri_h / 2)
            path.closeSubpath()
            p.drawPath(path)


class WaveBars(QWidget):
    def __init__(self, parent: Optional[QWidget] = None, *, bar_count: int = 4) -> None:
        super().__init__(parent)
        self._count = bar_count
        self.setFixedSize(22 if bar_count <= 4 else 26, 16)
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
        w, h = self.width(), self.height()
        bar_w, gap = 3.0, 2.4
        total = self._count * bar_w + (self._count - 1) * gap
        x0 = (w - total) / 2.0
        for i, level in enumerate(self._levels):
            bh = max(3.0, h * level)
            p.drawRoundedRect(QRectF(x0 + i * (bar_w + gap), h - bh, bar_w, bh), 1.4, 1.4)
        p.end()


class ControlsBar(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.prev_btn = IconButton("prev", self, size=40)
        self.play_btn = IconButton("pause", self, size=44)
        self.next_btn = IconButton("next", self, size=40)
        self.output_btn = IconButton("airplay", self, size=28)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        gap = 30
        play_w = self.play_btn.width()
        prev_w = self.prev_btn.width()
        next_w = self.next_btn.width()
        cluster = prev_w + gap + play_w + gap + next_w
        left = (w - cluster) / 2.0
        cy = h / 2.0
        self.prev_btn.move(int(left), int(cy - self.prev_btn.height() / 2))
        self.play_btn.move(int(left + prev_w + gap), int(cy - self.play_btn.height() / 2))
        self.next_btn.move(
            int(left + prev_w + gap + play_w + gap),
            int(cy - self.next_btn.height() / 2),
        )
        self.output_btn.move(int(w - self.output_btn.width() - 2), int(cy - self.output_btn.height() / 2))


class ClickAwayOverlay(QWidget):
    """Fullscreen transparent layer — click outside the island collapses it."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class IslandWindow(QWidget):
    media_updated = Signal(object)
    toast_received = Signal(object)
    phone_devices = Signal(object)
    phone_status = Signal(str)

    def __init__(self, version: str = "0.0.0") -> None:
        super().__init__()
        self._version = version
        self._settings = cfg.load()
        self._style: IsleStyle = get_style(str(self._settings.get("style_id") or "liquid_glass"))

        self.setObjectName("IsleWindow")
        self.setWindowTitle(f"Isle {version}")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        flags = (
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        if bool(self._settings.get("always_on_top", True)):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

        self._mode = IslandMode.IDLE
        self._hover = False
        self._media = MediaInfo()
        self._toast: Optional[ToastInfo] = None
        self._scrubbing = False
        self._accent = QColor(ACCENT_FALLBACK)
        self._settings_window: Optional[SettingsWindow] = None

        # Timer state
        self._timer_end: Optional[float] = None
        self._timer_total = 0

        self._overlay = ClickAwayOverlay()
        self._overlay.clicked.connect(self.collapse_from_outside)

        self._build_ui()
        self._wire_media()
        self._wire_phone()
        self._setup_tray()

        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.setDuration(ANIM_MS)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geo_anim.valueChanged.connect(lambda *_: self.update())

        self.media_updated.connect(self._apply_media)
        self.toast_received.connect(self._apply_toast)
        self.phone_devices.connect(self._on_phone_devices)
        self.phone_status.connect(self._on_phone_status)

        self._show_mode_widgets()
        self._place(self._style.idle)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._dismiss_toast)

        self._clock = QTimer(self)
        self._clock.setInterval(200)
        self._clock.timeout.connect(self._on_clock)
        self._clock.start()

        # Soft acrylic hint on Windows for liquid glass
        QTimer.singleShot(0, self._try_enable_blur)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.compact = QWidget(self)
        compact_l = QHBoxLayout(self.compact)
        compact_l.setContentsMargins(8, 0, 10, 0)
        compact_l.setSpacing(0)
        self.compact_cover = QLabel(self.compact)
        self.compact_cover.setFixedSize(28, 28)
        self.compact_bars = WaveBars(self.compact, bar_count=4)
        self.compact_timer = QLabel("", self.compact)
        self.compact_timer.setStyleSheet("color:#ffffff;font-size:12px;font-weight:600;")
        self.compact_timer.hide()
        compact_l.addWidget(self.compact_cover, 0, Qt.AlignVCenter)
        compact_l.addStretch(1)
        compact_l.addWidget(self.compact_timer, 0, Qt.AlignVCenter)
        compact_l.addWidget(self.compact_bars, 0, Qt.AlignVCenter)
        root.addWidget(self.compact)

        self.expanded = QWidget(self)
        exp = QVBoxLayout(self.expanded)
        exp.setContentsMargins(22, 18, 22, 14)
        exp.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.cover = QLabel(self.expanded)
        self.cover.setFixedSize(64, 64)
        meta = QVBoxLayout()
        meta.setSpacing(3)
        meta.setContentsMargins(0, 6, 0, 0)
        self.title_lbl = QLabel("Title", self.expanded)
        self.title_lbl.setStyleSheet("color:#ffffff;font-size:15px;font-weight:600;")
        self.title_lbl.setWordWrap(False)
        self.artist_lbl = QLabel("Artist", self.expanded)
        self.artist_lbl.setStyleSheet("color:#9a9a9a;font-size:13px;")
        meta.addWidget(self.title_lbl)
        meta.addWidget(self.artist_lbl)
        meta.addStretch(1)
        self.expanded_bars = WaveBars(self.expanded, bar_count=5)
        top.addWidget(self.cover, 0, Qt.AlignVCenter)
        top.addLayout(meta, 1)
        top.addWidget(self.expanded_bars, 0, Qt.AlignTop)
        exp.addLayout(top)
        exp.addSpacing(16)

        times = QHBoxLayout()
        times.setContentsMargins(1, 0, 1, 2)
        self.elapsed_lbl = QLabel("0:00", self.expanded)
        self.elapsed_lbl.setStyleSheet("color:#d0d0d0;font-size:11px;")
        self.remaining_lbl = QLabel("-0:00", self.expanded)
        self.remaining_lbl.setStyleSheet("color:#d0d0d0;font-size:11px;")
        self.remaining_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        times.addWidget(self.elapsed_lbl)
        times.addStretch(1)
        times.addWidget(self.remaining_lbl)
        exp.addLayout(times)

        self.scrubber = QSlider(Qt.Horizontal, self.expanded)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setFixedHeight(12)
        self.scrubber.setStyleSheet(
            """
            QSlider::groove:horizontal { height: 3px; background: #2a2a2a; border: none; border-radius: 1px; }
            QSlider::sub-page:horizontal { background: #8a8a8a; border-radius: 1px; }
            QSlider::handle:horizontal { width: 0px; height: 0px; margin: 0; background: transparent; border: none; }
            QSlider::handle:horizontal:hover {
                width: 8px; height: 8px; margin: -2px 0; background: #ffffff; border-radius: 4px;
            }
            """
        )
        self.scrubber.sliderPressed.connect(self._on_scrub_press)
        self.scrubber.sliderReleased.connect(self._on_scrub_release)
        self.scrubber.sliderMoved.connect(self._on_scrub_moved)
        exp.addWidget(self.scrubber)
        exp.addSpacing(10)

        self.controls = ControlsBar(self.expanded)
        self.controls.prev_btn.clicked.connect(self._on_prev)
        self.controls.play_btn.clicked.connect(self._on_play_pause)
        self.controls.next_btn.clicked.connect(self._on_next)
        self.controls.output_btn.clicked.connect(self._on_output)
        exp.addWidget(self.controls)
        root.addWidget(self.expanded)

        # Timer panel
        self.timer_panel = QWidget(self)
        tl = QVBoxLayout(self.timer_panel)
        tl.setContentsMargins(22, 18, 22, 16)
        self.timer_title = QLabel("Timer", self.timer_panel)
        self.timer_title.setStyleSheet("color:#9a9a9a;font-size:12px;")
        self.timer_value = QLabel("5:00", self.timer_panel)
        self.timer_value.setAlignment(Qt.AlignCenter)
        self.timer_value.setStyleSheet("color:#ffffff;font-size:36px;font-weight:600;")
        self.timer_stop = QPushButton("Stop", self.timer_panel)
        self.timer_stop.setCursor(Qt.PointingHandCursor)
        self.timer_stop.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.08); color:#fff; border:1px solid rgba(255,255,255,0.2);"
            " border-radius:10px; padding:8px 16px; }"
            "QPushButton:hover { border-color:#aaa; }"
        )
        self.timer_stop.clicked.connect(self.stop_timer)
        tl.addWidget(self.timer_title)
        tl.addStretch(1)
        tl.addWidget(self.timer_value)
        tl.addStretch(1)
        tl.addWidget(self.timer_stop, 0, Qt.AlignCenter)
        root.addWidget(self.timer_panel)

        # Toast
        self.toast_panel = QWidget(self)
        toast_l = QVBoxLayout(self.toast_panel)
        toast_l.setContentsMargins(16, 14, 16, 14)
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
        self.reply_edit = QLineEdit(self.whatsapp_row)
        self.reply_edit.setPlaceholderText("Reply (copies + opens WhatsApp)")
        self.reply_edit.setStyleSheet(
            "QLineEdit { background:rgba(0,0,0,0.35); color:#fff; border:1px solid rgba(255,255,255,0.18);"
            " padding:6px 8px; border-radius:6px; }"
        )
        self.reply_btn = QPushButton("Open", self.whatsapp_row)
        self.reply_btn.setCursor(Qt.PointingHandCursor)
        self.reply_btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.08); color:#fff; border:1px solid rgba(255,255,255,0.2);"
            " padding:6px 12px; border-radius:6px; }"
        )
        self.reply_btn.clicked.connect(self._on_whatsapp_reply)
        self.reply_edit.returnPressed.connect(self._on_whatsapp_reply)
        wa.addWidget(self.reply_edit, 1)
        wa.addWidget(self.reply_btn)
        self.whatsapp_row.hide()
        toast_l.addWidget(self.whatsapp_row)
        root.addWidget(self.toast_panel)

        self.setFont(QFont("Segoe UI", 10))

    def _wire_media(self) -> None:
        self._service = MediaService(
            on_media=lambda info: self.media_updated.emit(info),
            on_toast=lambda toast: self.toast_received.emit(toast),
            settings=self._settings,
        )
        self._service.start()

    def _wire_phone(self) -> None:
        self._phone = PhoneConnectService(
            on_devices=lambda devices: self.phone_devices.emit(devices),
            on_status=lambda text: self.phone_status.emit(text),
        )
        addr = str(self._settings.get("iphone_device_address") or "")
        self._phone.set_target(addr)
        if bool(self._settings.get("iphone_connect_enabled")):
            self._phone.start()

    def _setup_tray(self) -> None:
        pix = QPixmap(16, 16)
        pix.fill(QColor(30, 30, 30))
        self._tray = QSystemTrayIcon(QIcon(pix), self)
        self._tray.setToolTip(f"Isle {self._version}")
        menu = QMenu()
        about = QAction(f"Isle {self._version}", menu)
        about.setEnabled(False)
        menu.addAction(about)
        menu.addSeparator()
        setup_action = QAction("Setup…", menu)
        setup_action.triggered.connect(self.open_settings)
        menu.addAction(setup_action)
        timer_action = QAction("Start timer", menu)
        timer_action.triggered.connect(self.start_default_timer)
        menu.addAction(timer_action)
        stop_timer = QAction("Stop timer", menu)
        stop_timer.triggered.connect(self.stop_timer)
        menu.addAction(stop_timer)
        menu.addSeparator()
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
            self._settings_window.style_changed.connect(self.apply_style)
            self._settings_window.phone_target_changed.connect(self._on_phone_target)
            self._settings_window.set_bluetooth_hooks(refresh_cb=self._phone.refresh)
        self._settings_window.reload()
        self._settings_window.set_bluetooth_devices(self._phone.devices)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_changed(self, data: dict) -> None:
        self._settings = dict(data)
        self._service.apply_settings(self._settings)
        self.apply_style(str(data.get("style_id") or "liquid_glass"))
        enabled = bool(data.get("iphone_connect_enabled"))
        self._phone.set_target(str(data.get("iphone_device_address") or ""))
        if enabled:
            self._phone.start()
            self._phone.refresh()
        else:
            self._phone.stop()

    def _on_phone_target(self, address: str, _name: str) -> None:
        self._phone.set_target(address)
        self._phone.refresh()

    def _on_phone_devices(self, devices: List[BtDevice]) -> None:
        if self._settings_window is not None:
            self._settings_window.set_bluetooth_devices(devices)

    def _on_phone_status(self, text: str) -> None:
        if self._settings_window is not None:
            self._settings_window.set_phone_status(text)

    def _tray_open_youtube(self) -> None:
        webbrowser.open(str(self._settings.get("youtube_music_url") or "https://music.youtube.com"))

    def _tray_open_whatsapp(self) -> None:
        webbrowser.open(str(self._settings.get("whatsapp_uri") or "whatsapp:"))

    # ------------------------------------------------------------------
    # Style / geometry
    # ------------------------------------------------------------------

    def apply_style(self, style_id: str) -> None:
        self._style = get_style(style_id)
        self._try_enable_blur()
        self._recompute_mode(force=True)
        self.update()

    def _radius_for(self, size: QSize) -> float:
        if size.height() >= 100:
            return float(self._style.radius_expanded)
        if self._style.radius_idle > 0:
            return float(self._style.radius_idle)
        return min(size.width(), size.height()) / 2.0

    def _target_size(self) -> QSize:
        st = self._style
        if self._mode == IslandMode.EXPANDED:
            return QSize(st.expanded)
        if self._mode == IslandMode.COMPACT:
            return QSize(st.compact)
        if self._mode == IslandMode.TOAST:
            h = st.toast.height() + (40 if self._toast and self._toast.is_whatsapp else 0)
            return QSize(st.toast.width(), h)
        if self._mode == IslandMode.TIMER:
            return QSize(st.expanded.width() - 40, 160)
        return QSize(st.idle)

    def _centered_rect(self, size: QSize) -> QRect:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, self._style.top_margin, size.width(), size.height())
        geo = screen.geometry()
        x = geo.x() + (geo.width() - size.width()) // 2
        y = geo.y() + self._style.top_margin
        return QRect(x, y, size.width(), size.height())

    def _place(self, size: QSize) -> None:
        self.setGeometry(self._centered_rect(size))

    def _animate_to(self, size: QSize) -> None:
        target = self._centered_rect(size)
        if self.geometry() == target:
            return
        self._geo_anim.stop()
        self._geo_anim.setStartValue(self.geometry())
        self._geo_anim.setEndValue(target)
        self._geo_anim.start()

    def _try_enable_blur(self) -> None:
        """Best-effort Windows acrylic behind translucent glass styles."""
        if sys.platform != "win32" or not self._style.fill_glass:
            return
        try:
            import ctypes
            from ctypes import wintypes

            class ACCENTPOLICY(ctypes.Structure):
                _fields_ = [
                    ("AccentState", ctypes.c_int),
                    ("AccentFlags", ctypes.c_int),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_int),
                ]

            class WINCOMPATTRDATA(ctypes.Structure):
                _fields_ = [
                    ("Attribute", ctypes.c_int),
                    ("Data", ctypes.c_void_p),
                    ("SizeOfData", ctypes.c_size_t),
                ]

            # ACCENT_ENABLE_ACRYLICBLURBEHIND = 4; gradient ABGR
            accent = ACCENTPOLICY()
            accent.AccentState = 4
            accent.AccentFlags = 2
            accent.GradientColor = 0x33202020
            data = WINCOMPATTRDATA()
            data.Attribute = 19  # WCA_ACCENT_POLICY
            data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
            data.SizeOfData = ctypes.sizeof(accent)
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        except Exception:
            log.debug("acrylic blur unavailable", exc_info=True)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = self._radius_for(self.size())
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        st = self._style
        if st.fill_glass:
            # Liquid glass: translucent body + specular wash (Apple-like).
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(st.fill))
            p.drawPath(path)
            if st.specular:
                grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                grad.setColorAt(0.0, QColor(255, 255, 255, 70))
                grad.setColorAt(0.35, QColor(255, 255, 255, 18))
                grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(grad))
                p.drawPath(path)
                # Soft bottom depth
                depth = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                depth.setColorAt(0.55, QColor(0, 0, 0, 0))
                depth.setColorAt(1.0, QColor(0, 0, 0, 40))
                p.setBrush(QBrush(depth))
                p.drawPath(path)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(st.fill))
            p.drawPath(path)

        show_rim = self._hover or self._mode in (
            IslandMode.EXPANDED,
            IslandMode.TOAST,
            IslandMode.TIMER,
            IslandMode.COMPACT,
        )
        if show_rim:
            pen = QPen(st.rim)
            pen.setWidthF(st.rim_width if self._hover else max(1.0, st.rim_width * 0.7))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            if self._hover or st.fill_glass:
                inner = QRectF(self.rect()).adjusted(2.2, 2.2, -2.2, -2.2)
                ip = QPainterPath()
                ip.addRoundedRect(inner, max(2.0, r - 2.0), max(2.0, r - 2.0))
                ipen = QPen(st.inner)
                ipen.setWidthF(1.0)
                p.setPen(ipen)
                p.drawPath(ip)
        p.end()

    # ------------------------------------------------------------------
    # Modes — hover open / leave or click-away close
    # ------------------------------------------------------------------

    def _show_mode_widgets(self) -> None:
        self.compact.setVisible(self._mode == IslandMode.COMPACT)
        self.expanded.setVisible(self._mode == IslandMode.EXPANDED)
        self.toast_panel.setVisible(self._mode == IslandMode.TOAST)
        self.timer_panel.setVisible(self._mode == IslandMode.TIMER)
        # Idle: empty pill (Samsung Dot = just the dot).
        media_bits = self._mode == IslandMode.COMPACT and self._media.active
        self.compact_cover.setVisible(media_bits and self._timer_end is None)
        self.compact_bars.setVisible(media_bits and self._timer_end is None)
        self.compact_timer.setVisible(self._mode == IslandMode.COMPACT and self._timer_end is not None)
        self._sync_overlay()

    def _sync_overlay(self) -> None:
        """Show click-away layer only while the island is expanded / toast / timer."""
        need = self._mode in (IslandMode.EXPANDED, IslandMode.TOAST, IslandMode.TIMER)
        if need:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self._overlay.setGeometry(screen.geometry())
            self._overlay.show()
            self._overlay.raise_()
            self.raise_()
            self.activateWindow()
        else:
            self._overlay.hide()

    def _recompute_mode(self, force: bool = False) -> None:
        if self._mode == IslandMode.TOAST and self._toast is not None and not force:
            pass
        elif self._hover:
            if self._timer_end is not None and not self._media.active:
                self._mode = IslandMode.TIMER
            elif self._media.active:
                self._mode = IslandMode.EXPANDED
            elif self._timer_end is not None:
                self._mode = IslandMode.TIMER
            else:
                self._mode = IslandMode.IDLE
        else:
            if self._timer_end is not None:
                self._mode = IslandMode.COMPACT
            elif self._media.active:
                self._mode = IslandMode.COMPACT
            else:
                self._mode = IslandMode.IDLE

        self._show_mode_widgets()
        self._animate_to(self._target_size())

    def collapse_from_outside(self) -> None:
        """Click-away: collapse expanded / toast / timer detail."""
        self._hover = False
        self._toast = None
        self.whatsapp_row.hide()
        self._toast_timer.stop()
        self._recompute_mode(force=True)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        self._recompute_mode()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        if self._mode != IslandMode.TOAST:
            self._recompute_mode()
        super().leaveEvent(event)

    # ------------------------------------------------------------------
    # Media / toast / timer
    # ------------------------------------------------------------------

    def _apply_media(self, info: MediaInfo) -> None:
        self._media = info
        self._update_media_widgets()
        if self._mode != IslandMode.TOAST:
            self._recompute_mode()

    def _elide(self, label: QLabel, text: str) -> None:
        metrics = QFontMetrics(label.font())
        width = max(80, self._style.expanded.width() - 22 * 2 - 64 - 14 - 30 - 8)
        label.setText(metrics.elidedText(text, Qt.ElideRight, width))

    def _update_media_widgets(self) -> None:
        info = self._media
        image = QImage.fromData(info.thumbnail) if info.thumbnail else QImage()
        self._accent = _accent_from_image(image) if not image.isNull() else QColor(ACCENT_FALLBACK)
        if image.isNull():
            blank = QPixmap(64, 64)
            blank.fill(QColor("#1a1a1a"))
            cover_pix = _rounded_pixmap(blank, 64, 12)
            compact_pix = _rounded_pixmap(blank, 28, 7)
        else:
            full = QPixmap.fromImage(image)
            cover_pix = _rounded_pixmap(full, 64, 12)
            compact_pix = _rounded_pixmap(full, 28, 7)
        self.cover.setPixmap(cover_pix)
        self.compact_cover.setPixmap(compact_pix)
        self.compact_bars.set_accent(self._accent)
        self.compact_bars.set_playing(info.playing)
        self.expanded_bars.set_accent(self._accent)
        self.expanded_bars.set_playing(info.playing)
        self._elide(self.title_lbl, info.title or "Unknown")
        self._elide(self.artist_lbl, info.artist or "")
        self.controls.play_btn.set_kind("pause" if info.playing else "play")
        self.controls.prev_btn.setEnabled(info.can_skip_previous)
        self.controls.next_btn.setEnabled(info.can_skip_next)
        self.controls.play_btn.setEnabled(info.can_play_pause or info.active)
        self.scrubber.setEnabled(info.can_seek)
        if not self._scrubbing:
            duration = max(info.duration, 0.0)
            pos = max(0.0, min(info.position, duration if duration else info.position))
            self.elapsed_lbl.setText(_format_time(pos))
            remain = max(0.0, duration - pos) if duration else 0.0
            self.remaining_lbl.setText(f"-{_format_time(remain)}")
            self.scrubber.setValue(int((pos / duration) * 1000) if duration > 0 else 0)

    def _apply_toast(self, toast: ToastInfo) -> None:
        if toast.is_whatsapp and not bool(self._settings.get("whatsapp_toasts_enabled", True)):
            return
        self._toast = toast
        self.toast_app.setText(toast.app or "Notification")
        self.toast_title.setText(toast.title or "")
        self.toast_body.setText(toast.body or "")
        show_reply = toast.is_whatsapp and bool(self._settings.get("whatsapp_reply_enabled", True))
        self.whatsapp_row.setVisible(show_reply)
        if show_reply:
            self.reply_edit.clear()
        self._mode = IslandMode.TOAST
        self._show_mode_widgets()
        self._animate_to(self._target_size())
        self._toast_timer.start(8000)

    def _dismiss_toast(self) -> None:
        self._toast = None
        self.whatsapp_row.hide()
        if self._mode == IslandMode.TOAST:
            self._recompute_mode(force=True)

    def start_default_timer(self) -> None:
        mins = int(self._settings.get("timer_default_minutes") or 5)
        self.start_timer(mins * 60)

    def start_timer(self, seconds: int) -> None:
        self._timer_total = max(1, int(seconds))
        self._timer_end = time.time() + self._timer_total
        self._update_timer_labels()
        self._recompute_mode(force=True)

    def stop_timer(self) -> None:
        self._timer_end = None
        self._timer_total = 0
        self.compact_timer.hide()
        self._recompute_mode(force=True)

    def _update_timer_labels(self) -> None:
        if self._timer_end is None:
            return
        left = max(0, int(self._timer_end - time.time()))
        text = _format_time(left)
        self.timer_value.setText(text)
        self.compact_timer.setText(text)

    def _on_clock(self) -> None:
        if self._timer_end is None:
            return
        if time.time() >= self._timer_end:
            self._timer_end = None
            self._tray.showMessage("Isle Timer", "Time is up", QSystemTrayIcon.MessageIcon.Information, 4000)
            self._recompute_mode(force=True)
            return
        self._update_timer_labels()

    def _on_play_pause(self) -> None:
        self._service.toggle_play_pause()

    def _on_next(self) -> None:
        self._service.skip_next()

    def _on_prev(self) -> None:
        self._service.skip_previous()

    def _on_output(self) -> None:
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
            self._overlay.hide()
            self._overlay.close()
        except Exception:
            pass
        try:
            self._service.stop()
        except Exception:
            pass
        try:
            self._phone.stop()
        except Exception:
            pass
        if hasattr(self, "_tray"):
            self._tray.hide()
        if self._settings_window is not None:
            self._settings_window.close()
        super().closeEvent(event)


class SingleInstance:
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


def run(version: str = "0.0.0") -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Isle")
    app.setApplicationVersion(version)
    app.setOrganizationName("Quickr")

    guard = SingleInstance()
    if not guard.acquire():
        log.error("Isle is already running")
        return 1

    window = IslandWindow(version=version)
    window.show()

    code = app.exec()
    guard.release()
    return code
