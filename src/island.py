"""PySide6 Dynamic Island window for Windows (Isle).

Frameless, always-on-top tool window at the top-center of the primary screen.
Idle / compact / expanded sizes with OutCubic size animation.
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

from media import MediaInfo, MediaService, ToastInfo

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


class FlatBars(QWidget):
    """Four flat white equalizer-style bars for the compact pill."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(22, 16)
        self._levels = [0.35, 0.7, 0.45, 0.85]
        self._playing = False
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        if playing:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._levels = [0.25, 0.25, 0.25, 0.25]
            self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 1) % 8
        # Deterministic soft bounce — still "flat" bars, not a gradient fill.
        pattern = (
            (0.3, 0.8, 0.45, 0.7),
            (0.55, 0.4, 0.85, 0.35),
            (0.75, 0.55, 0.3, 0.9),
            (0.4, 0.95, 0.6, 0.45),
            (0.65, 0.35, 0.8, 0.55),
            (0.35, 0.7, 0.5, 0.85),
            (0.85, 0.5, 0.35, 0.6),
            (0.5, 0.65, 0.9, 0.4),
        )
        self._levels = list(pattern[self._phase])
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(WHITE))
        w = self.width()
        h = self.height()
        bar_w = 3
        gap = 3
        total = 4 * bar_w + 3 * gap
        x0 = (w - total) // 2
        for i, level in enumerate(self._levels):
            bh = max(2, int(h * level))
            x = x0 + i * (bar_w + gap)
            y = h - bh
            p.drawRect(x, y, bar_w, bh)
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

        # Compact row
        self.compact = QWidget(self)
        compact_l = QHBoxLayout(self.compact)
        compact_l.setContentsMargins(0, 0, 0, 0)
        compact_l.setSpacing(10)
        self.compact_cover = QLabel(self.compact)
        self.compact_cover.setFixedSize(28, 28)
        self.compact_cover.setScaledContents(True)
        self.compact_bars = FlatBars(self.compact)
        compact_l.addWidget(self.compact_cover)
        compact_l.addStretch(1)
        compact_l.addWidget(self.compact_bars)
        root.addWidget(self.compact)

        # Expanded media panel
        self.expanded = QWidget(self)
        exp = QVBoxLayout(self.expanded)
        exp.setContentsMargins(0, 0, 0, 0)
        exp.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.cover = QLabel(self.expanded)
        self.cover.setFixedSize(96, 96)
        self.cover.setScaledContents(True)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        self.title_lbl = QLabel("Title", self.expanded)
        self.title_lbl.setStyleSheet("color:#ffffff;font-size:15px;font-weight:600;")
        self.title_lbl.setWordWrap(True)
        self.artist_lbl = QLabel("Artist", self.expanded)
        self.artist_lbl.setStyleSheet("color:#c8c8c8;font-size:12px;")
        self.source_lbl = QLabel("Source", self.expanded)
        self.source_lbl.setStyleSheet("color:#8a8a8a;font-size:11px;")
        meta.addWidget(self.title_lbl)
        meta.addWidget(self.artist_lbl)
        meta.addWidget(self.source_lbl)
        meta.addStretch(1)
        top.addWidget(self.cover)
        top.addLayout(meta, 1)
        exp.addLayout(top)

        times = QHBoxLayout()
        self.elapsed_lbl = QLabel("0:00", self.expanded)
        self.elapsed_lbl.setStyleSheet("color:#b0b0b0;font-size:11px;")
        self.remaining_lbl = QLabel("-0:00", self.expanded)
        self.remaining_lbl.setStyleSheet("color:#b0b0b0;font-size:11px;")
        self.remaining_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        times.addWidget(self.elapsed_lbl)
        times.addStretch(1)
        times.addWidget(self.remaining_lbl)
        exp.addLayout(times)

        self.scrubber = QSlider(Qt.Horizontal, self.expanded)
        self.scrubber.setRange(0, 1000)
        self.scrubber.setFixedHeight(16)
        self.scrubber.setStyleSheet(
            """
            QSlider::groove:horizontal {
                height: 3px;
                background: #3a3a3a;
                border: none;
            }
            QSlider::handle:horizontal {
                width: 10px;
                height: 10px;
                margin: -4px 0;
                background: #ffffff;
                border: none;
            }
            QSlider::sub-page:horizontal {
                background: #ffffff;
            }
            """
        )
        self.scrubber.sliderPressed.connect(self._on_scrub_press)
        self.scrubber.sliderReleased.connect(self._on_scrub_release)
        self.scrubber.sliderMoved.connect(self._on_scrub_moved)
        exp.addWidget(self.scrubber)

        controls = QHBoxLayout()
        controls.setSpacing(18)
        controls.addStretch(1)
        self.prev_btn = self._control_button("⏮", self._on_prev)
        self.play_btn = self._control_button("⏯", self._on_play_pause)
        self.next_btn = self._control_button("⏭", self._on_next)
        controls.addWidget(self.prev_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addStretch(1)
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
            " padding:6px 8px; }"
        )
        self.reply_btn = QPushButton("Open", self.whatsapp_row)
        self.reply_btn.setCursor(Qt.PointingHandCursor)
        self.reply_btn.setStyleSheet(
            "QPushButton { background:#1a1a1a; color:#fff; border:1px solid #444;"
            " padding:6px 12px; }"
            "QPushButton:hover { border-color:#888; }"
        )
        self.reply_btn.clicked.connect(self._on_whatsapp_reply)
        self.reply_edit.returnPressed.connect(self._on_whatsapp_reply)
        wa.addWidget(self.reply_edit, 1)
        wa.addWidget(self.reply_btn)
        self.whatsapp_row.hide()
        toast_l.addWidget(self.whatsapp_row)
        root.addWidget(self.toast_panel)

        for w in (
            self,
            self.compact,
            self.expanded,
            self.toast_panel,
            self.title_lbl,
            self.artist_lbl,
            self.source_lbl,
        ):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        font = QFont("Segoe UI", 10)
        self.setFont(font)

    def _control_button(self, text: str, slot) -> QPushButton:
        btn = QPushButton(text, self.expanded)
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: transparent; color: #ffffff; border: none;"
            " font-size: 16px; }"
            "QPushButton:hover { color: #dddddd; }"
            "QPushButton:disabled { color: #555555; }"
        )
        btn.clicked.connect(slot)
        return btn

    def _wire_media(self) -> None:
        self._service = MediaService(
            on_media=lambda info: self.media_updated.emit(info),
            on_toast=lambda toast: self.toast_received.emit(toast),
        )
        self._service.start()

    def _setup_tray(self) -> None:
        # Tiny black pixmap so the tray always has an icon.
        pix = QPixmap(16, 16)
        pix.fill(FILL)
        self._tray = QSystemTrayIcon(QIcon(pix), self)
        self._tray.setToolTip("Isle")
        menu = QMenu()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()

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

        if self._hover or self._pinned or self._mode in (IslandMode.EXPANDED, IslandMode.TOAST):
            # 1.4px white rim
            pen = QPen(RIM)
            pen.setWidthF(1.4)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            # Faint inner stroke
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
        # Idle: empty black pill — no child widgets.
        margins = {
            IslandMode.IDLE: (0, 0, 0, 0),
            IslandMode.COMPACT: (14, 8, 14, 8),
            IslandMode.EXPANDED: (18, 16, 18, 16),
            IslandMode.TOAST: (16, 14, 16, 14),
        }[self._mode]
        self.layout().setContentsMargins(*margins)

    def _recompute_mode(self) -> None:
        if self._toast is not None and self._mode == IslandMode.TOAST:
            # Stay on toast until dismissed unless pinned expansion requested.
            pass
        elif self._pinned or (self._hover and self._media.active):
            if self._media.active:
                self._mode = IslandMode.EXPANDED
            else:
                self._mode = IslandMode.IDLE
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
        pix = self._pixmap_from_bytes(info.thumbnail, 96)
        if pix is None:
            blank = QPixmap(96, 96)
            blank.fill(QColor("#1a1a1a"))
            pix = blank
        self.cover.setPixmap(pix)
        self.compact_cover.setPixmap(pix.scaled(28, 28, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self.compact_bars.set_playing(info.playing)

        self.title_lbl.setText(info.title or "Unknown")
        self.artist_lbl.setText(info.artist or "")
        self.source_lbl.setText(info.source or "")
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

    def _pixmap_from_bytes(self, data: bytes, size: int) -> Optional[QPixmap]:
        if not data:
            return None
        image = QImage.fromData(data)
        if image.isNull():
            return None
        return QPixmap.fromImage(image).scaled(
            size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )

    def _apply_toast(self, toast: ToastInfo) -> None:
        self._toast = toast
        self.toast_app.setText(toast.app or "Notification")
        self.toast_title.setText(toast.title or "")
        self.toast_body.setText(toast.body or "")
        if toast.is_whatsapp:
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
            if self._media.active:
                self._mode = IslandMode.COMPACT
            else:
                self._mode = IslandMode.IDLE
            self._show_mode_widgets()
            self._animate_to(self._target_size())
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            # Clicking empty black pins/unpins expanded state.
            child = self.childAt(event.position().toPoint())
            interactive = (
                self.prev_btn,
                self.play_btn,
                self.next_btn,
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
        text = self.reply_edit.text().strip()
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        webbrowser.open("whatsapp:")
        self.reply_edit.clear()

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._service.stop()
        except Exception:
            pass
        if hasattr(self, "_tray"):
            self._tray.hide()
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
    # High-DPI friendly defaults
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
