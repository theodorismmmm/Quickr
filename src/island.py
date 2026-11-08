"""PySide6 Dynamic Island window for Windows (Isle).

Frameless, always-on-top tool window at the top-center of the primary screen.
Idle / compact / expanded sizes with OutCubic geometry animation (stays centered).
Drawn vector transport icons (no emoji). Adaptive: click-through when idle and
auto-hides over fullscreen apps so it does not block other windows.
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
EXPANDED_SIZE = QSize(420, 220)
ANIM_MS = 320
TOP_MARGIN = 8
FILL = QColor("#000000")
RIM = QColor(255, 255, 255, 210)
INNER = QColor(255, 255, 255, 40)
WHITE = QColor(255, 255, 255)
MUTED = QColor(180, 180, 180)
ACCENT_FALLBACK = QColor(210, 145, 175)


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


# ---------------------------------------------------------------------------
# Drawn icons (no emoji)
# ---------------------------------------------------------------------------


class IconButton(QWidget):
    """Flat white transport / output icon drawn with QPainter."""

    clicked = Signal()

    def __init__(self, kind: str, parent: Optional[QWidget] = None, *, size: int = 40) -> None:
        super().__init__(parent)
        self._kind = kind  # prev | play | pause | next | airplay
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
        if event.button() == Qt.LeftButton and self._enabled and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._enabled:
            color = QColor(70, 70, 70)
        elif self._hover:
            color = QColor(230, 230, 230)
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
            self._draw_airplay(p, cx, cy, color)

        p.end()

    def _draw_skip(self, p: QPainter, cx: float, cy: float, *, left: bool) -> None:
        # Double triangle + bar, matching iOS media controls.
        sign = -1.0 if left else 1.0
        bar_w, bar_h = 2.4, 15.0
        tri_w, tri_h = 8.5, 15.0
        # bar at the outer edge
        bar_x = cx + sign * 9.0 - (bar_w if sign > 0 else 0)
        p.drawRoundedRect(QRectF(bar_x, cy - bar_h / 2, bar_w, bar_h), 0.8, 0.8)
        # two chevrons
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

    def _draw_airplay(self, p: QPainter, cx: float, cy: float, color: QColor) -> None:
        pen = QPen(color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # concentric arcs
        for i, r in enumerate((5.5, 9.0)):
            rect = QRectF(cx - r, cy - r - 2, r * 2, r * 2)
            p.drawArc(rect, 40 * 16, 100 * 16)
        # filled triangle / screen wedge
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        tri = QPainterPath()
        tri.moveTo(cx, cy + 2)
        tri.lineTo(cx - 6, cy + 10)
        tri.lineTo(cx + 6, cy + 10)
        tri.closeSubpath()
        p.drawPath(tri)


class WaveBars(QWidget):
    """Equalizer bars — rounded, accent-tinted like the reference photos."""

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
            x = x0 + i * (bar_w + gap)
            p.drawRoundedRect(QRectF(x, h - bh, bar_w, bh), 1.4, 1.4)
        p.end()


class ControlsBar(QWidget):
    """Prev / play-pause / next truly centered; AirPlay anchored to the right."""

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
        self.output_btn.move(
            int(w - self.output_btn.width() - 2),
            int(cy - self.output_btn.height() / 2),
        )


# ---------------------------------------------------------------------------
# Adaptive helpers (Windows)
# ---------------------------------------------------------------------------


def _set_click_through(widget: QWidget, enabled: bool) -> None:
    """Let clicks pass through to apps underneath when the island is idle."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        log.debug("click-through toggle failed", exc_info=True)


def _foreground_is_fullscreen(our_hwnd: int = 0) -> bool:
    """True when the foreground app covers the whole monitor (games / video)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or (our_hwnd and hwnd == our_hwnd):
            return False

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        info = ctypes.create_string_buffer(40 + 16)  # MONITORINFO roughly
        # Use GetSystemMetrics as a simpler fullscreen check.
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        # Treat near-full-screen as fullscreen (ignore 1px borders).
        if width >= sw - 2 and height >= sh - 2:
            return True
        # Maximized overlapping work area top strip heavily
        if width >= sw - 16 and height >= sh - 80 and rect.top <= 0:
            # Only dodge if the window occupies the island band.
            return rect.top <= TOP_MARGIN + 4
        _ = monitor, info
        return False
    except Exception:
        return False


class IslandWindow(QWidget):
    """Top-center Dynamic Island chrome."""

    media_updated = Signal(object)
    toast_received = Signal(object)

    def __init__(self, version: str = "0.0.0") -> None:
        super().__init__()
        self._version = version
        self.setObjectName("IsleWindow")
        self.setWindowTitle(f"Isle {version}")
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
        self._hidden_for_fullscreen = False
        self._click_through = False
        self._media = MediaInfo()
        self._toast: Optional[ToastInfo] = None
        self._scrubbing = False
        self._accent = QColor(ACCENT_FALLBACK)
        self._settings = cfg.load()
        self._settings_window: Optional[SettingsWindow] = None

        self._build_ui()
        self._wire_media()
        self._setup_tray()

        # Animate full geometry so the pill stays horizontally centered.
        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.setDuration(ANIM_MS)
        self._geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._geo_anim.valueChanged.connect(lambda *_: self.update())

        self.media_updated.connect(self._apply_media)
        self.toast_received.connect(self._apply_toast)

        self.resize(IDLE_SIZE)
        self._show_mode_widgets()
        self._place(IDLE_SIZE)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._dismiss_toast)

        # Proximity + fullscreen adaptation (works with click-through).
        self._adapt_timer = QTimer(self)
        self._adapt_timer.setInterval(60)
        self._adapt_timer.timeout.connect(self._adapt_tick)
        self._adapt_timer.start()

        QTimer.singleShot(0, lambda: self._set_click_through(True))

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Compact: cover left · empty · bars right, vertically centered
        self.compact = QWidget(self)
        compact_l = QHBoxLayout(self.compact)
        compact_l.setContentsMargins(8, 0, 10, 0)
        compact_l.setSpacing(0)
        self.compact_cover = QLabel(self.compact)
        self.compact_cover.setFixedSize(28, 28)
        self.compact_cover.setAlignment(Qt.AlignCenter)
        self.compact_bars = WaveBars(self.compact, bar_count=4)
        compact_l.addWidget(self.compact_cover, 0, Qt.AlignVCenter)
        compact_l.addStretch(1)
        compact_l.addWidget(self.compact_bars, 0, Qt.AlignVCenter)
        root.addWidget(self.compact)

        # Expanded
        self.expanded = QWidget(self)
        exp = QVBoxLayout(self.expanded)
        exp.setContentsMargins(22, 18, 22, 14)
        exp.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.setContentsMargins(0, 0, 0, 0)
        self.cover = QLabel(self.expanded)
        self.cover.setFixedSize(64, 64)
        meta = QVBoxLayout()
        meta.setSpacing(3)
        meta.setContentsMargins(0, 6, 0, 0)
        self.title_lbl = QLabel("Title", self.expanded)
        self.title_lbl.setStyleSheet(
            "color:#ffffff;font-size:15px;font-weight:600;letter-spacing:-0.2px;"
        )
        self.title_lbl.setWordWrap(False)
        self.artist_lbl = QLabel("Artist", self.expanded)
        self.artist_lbl.setStyleSheet("color:#9a9a9a;font-size:13px;")
        self.artist_lbl.setWordWrap(False)
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
            QSlider::groove:horizontal {
                height: 3px;
                background: #2a2a2a;
                border: none;
                border-radius: 1px;
            }
            QSlider::sub-page:horizontal {
                background: #8a8a8a;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                width: 0px; height: 0px; margin: 0;
                background: transparent; border: none;
            }
            QSlider::handle:horizontal:hover {
                width: 8px; height: 8px; margin: -2px 0;
                background: #ffffff; border-radius: 4px;
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

        self.setFont(QFont("Segoe UI", 10))

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
        self._tray.setToolTip(f"Isle {self._version}")
        menu = QMenu()
        about = QAction(f"Isle {self._version}", menu)
        about.setEnabled(False)
        menu.addAction(about)
        menu.addSeparator()
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
        self._set_click_through(False)
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
    # Geometry (always horizontally centered)
    # ------------------------------------------------------------------

    def _target_size(self) -> QSize:
        if self._mode == IslandMode.EXPANDED:
            return QSize(EXPANDED_SIZE)
        if self._mode == IslandMode.COMPACT:
            return QSize(COMPACT_SIZE)
        if self._mode == IslandMode.TOAST:
            h = 118 if not (self._toast and self._toast.is_whatsapp) else 164
            return QSize(360, h)
        return QSize(IDLE_SIZE)

    def _radius_for(self, size: QSize) -> float:
        if size.height() >= 100:
            return 40.0
        return min(size.width(), size.height()) / 2.0

    def _centered_rect(self, size: QSize) -> QRect:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, TOP_MARGIN, size.width(), size.height())
        # Use full geometry so the island sits in the true top-center (not
        # shifted by taskbar / reserved work-area quirks).
        geo = screen.geometry()
        x = geo.x() + (geo.width() - size.width()) // 2
        y = geo.y() + TOP_MARGIN
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

        if self._mode == IslandMode.COMPACT and not self._hover:
            pen = QPen(QColor(255, 255, 255, 30))
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
            inner_path.addRoundedRect(inner, max(2.0, r - 2.0), max(2.0, r - 2.0))
            ipen = QPen(INNER)
            ipen.setWidthF(1.0)
            p.setPen(ipen)
            p.drawPath(inner_path)
        p.end()

    # ------------------------------------------------------------------
    # Adaptive behaviour
    # ------------------------------------------------------------------

    def _set_click_through(self, enabled: bool) -> None:
        if self._click_through == enabled:
            return
        self._click_through = enabled
        _set_click_through(self, enabled)

    def _adapt_tick(self) -> None:
        # Hide over fullscreen apps so Isle never covers games / video.
        try:
            hwnd = int(self.winId()) if self.winId() else 0
        except Exception:
            hwnd = 0
        fs = _foreground_is_fullscreen(hwnd)
        if fs and not self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = True
            self.hide()
            return
        if not fs and self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = False
            self.show()

        if self._hidden_for_fullscreen:
            return

        # Cursor proximity drives hover even while click-through is on.
        pos = QCursor.pos()
        # Inflate hit area slightly so approaching the pill re-enables input.
        hit = self.geometry().adjusted(-28, -10, 28, 28)
        near = hit.contains(pos)

        if near and not self._hover:
            self._set_click_through(False)
            self._hover = True
            self.update()
            if self._mode != IslandMode.TOAST and self._media.active:
                self._mode = IslandMode.EXPANDED
                self._show_mode_widgets()
                self._animate_to(self._target_size())
        elif not near and self._hover and not self._pinned:
            self._hover = False
            self.update()
            if self._mode != IslandMode.TOAST:
                self._mode = IslandMode.COMPACT if self._media.active else IslandMode.IDLE
                self._show_mode_widgets()
                self._animate_to(self._target_size())
            # Pass clicks to underlying apps when collapsed away from cursor.
            if self._mode in (IslandMode.IDLE, IslandMode.COMPACT):
                self._set_click_through(True)

    # ------------------------------------------------------------------
    # Mode / content
    # ------------------------------------------------------------------

    def _show_mode_widgets(self) -> None:
        self.compact.setVisible(self._mode == IslandMode.COMPACT)
        self.expanded.setVisible(self._mode == IslandMode.EXPANDED)
        self.toast_panel.setVisible(self._mode == IslandMode.TOAST)

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
        if self._mode in (IslandMode.IDLE, IslandMode.COMPACT) and not self._hover:
            self._set_click_through(True)
        else:
            self._set_click_through(False)

    def _apply_media(self, info: MediaInfo) -> None:
        self._media = info
        self._update_media_widgets()
        if self._mode != IslandMode.TOAST:
            self._recompute_mode()

    def _elide(self, label: QLabel, text: str) -> None:
        metrics = QFontMetrics(label.font())
        # Leave room for cover + bars + padding inside expanded width.
        width = max(80, EXPANDED_SIZE.width() - 22 * 2 - 64 - 14 - 30 - 8)
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
        self._set_click_through(False)
        self._toast = toast
        self.toast_app.setText(toast.app or "Notification")
        self.toast_title.setText(toast.title or "")
        self.toast_body.setText(toast.body or "")
        show_reply = toast.is_whatsapp and bool(
            self._settings.get("whatsapp_reply_enabled", True)
        )
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
            self._recompute_mode()

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._media.active:
            child = self.childAt(event.position().toPoint())
            interactive = (
                self.controls.prev_btn,
                self.controls.play_btn,
                self.controls.next_btn,
                self.controls.output_btn,
                self.scrubber,
                self.reply_edit,
                self.reply_btn,
            )
            on_control = False
            w = child
            while w is not None:
                if w in interactive:
                    on_control = True
                    break
                w = w.parentWidget()
            if not on_control:
                self._pinned = not self._pinned
                if self._pinned:
                    self._mode = IslandMode.EXPANDED
                    self._set_click_through(False)
                elif not self._hover:
                    self._mode = IslandMode.COMPACT
                self._show_mode_widgets()
                self._animate_to(self._target_size())
                self.update()
        super().mousePressEvent(event)

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
            self._service.stop()
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
