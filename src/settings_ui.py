"""Separate tray Settings window for YouTube Music + WhatsApp setup."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import isle_settings as cfg


class SettingsWindow(QWidget):
    """Taskbar/tray companion UI — not the island itself."""

    def __init__(
        self,
        on_changed: Optional[Callable[[dict], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self.setWindowTitle("Isle Setup")
        self.setMinimumWidth(420)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.setStyleSheet(
            """
            QWidget { background: #111111; color: #f0f0f0; }
            QGroupBox {
                border: 1px solid #2a2a2a;
                border-radius: 10px;
                margin-top: 14px;
                padding: 12px 12px 10px 12px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #ffffff;
            }
            QCheckBox { spacing: 8px; }
            QLineEdit {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 7px 9px;
                color: #fff;
            }
            QPushButton {
                background: #1c1c1c;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 8px 14px;
                color: #fff;
            }
            QPushButton:hover { border-color: #777; }
            QLabel#hint { color: #9a9a9a; font-size: 12px; }
            """
        )
        self._build()
        self.reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Isle connections")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        subtitle = QLabel(
            "Configure YouTube Music and WhatsApp from the tray. "
            "These settings do not scrape apps — media still comes from the "
            "Windows media session, and WhatsApp reply only copies text."
        )
        subtitle.setObjectName("hint")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # ---- YouTube Music ----
        yt = QGroupBox("YouTube Music")
        yt_l = QVBoxLayout(yt)
        self.yt_enabled = QCheckBox("Show YouTube Music in the island")
        self.yt_prefer = QCheckBox("Prefer YouTube Music when several players are active")
        self.yt_url = QLineEdit()
        self.yt_url.setPlaceholderText("https://music.youtube.com")
        form = QFormLayout()
        form.addRow("Open URL", self.yt_url)
        yt_l.addWidget(self.yt_enabled)
        yt_l.addWidget(self.yt_prefer)
        yt_l.addLayout(form)
        yt_hint = QLabel(
            "Play a track in YouTube Music (app or browser). Windows then exposes "
            "it through the system media session — no per-app scraping."
        )
        yt_hint.setObjectName("hint")
        yt_hint.setWordWrap(True)
        yt_l.addWidget(yt_hint)
        yt_btns = QHBoxLayout()
        open_yt = QPushButton("Open YouTube Music")
        open_yt.clicked.connect(self._open_youtube_music)
        yt_btns.addWidget(open_yt)
        yt_btns.addStretch(1)
        yt_l.addLayout(yt_btns)
        root.addWidget(yt)

        # ---- WhatsApp ----
        wa = QGroupBox("WhatsApp")
        wa_l = QVBoxLayout(wa)
        self.wa_toasts = QCheckBox("Show WhatsApp toasts in the island")
        self.wa_reply = QCheckBox("Show reply field (copies text + opens whatsapp:)")
        self.wa_uri = QLineEdit()
        self.wa_uri.setPlaceholderText("whatsapp:")
        wa_form = QFormLayout()
        wa_form.addRow("Launch URI", self.wa_uri)
        wa_l.addWidget(self.wa_toasts)
        wa_l.addWidget(self.wa_reply)
        wa_l.addLayout(wa_form)
        wa_hint = QLabel(
            "Reply copies your text to the clipboard and opens the WhatsApp "
            "protocol handler. It does not send the toast’s inline reply and "
            "does not automate WhatsApp Web."
        )
        wa_hint.setObjectName("hint")
        wa_hint.setWordWrap(True)
        wa_l.addWidget(wa_hint)
        wa_btns = QHBoxLayout()
        open_wa = QPushButton("Open WhatsApp")
        open_wa.clicked.connect(self._open_whatsapp)
        notif = QPushButton("Notification access…")
        notif.clicked.connect(self._open_notification_settings)
        wa_btns.addWidget(open_wa)
        wa_btns.addWidget(notif)
        wa_btns.addStretch(1)
        wa_l.addLayout(wa_btns)
        root.addWidget(wa)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(save_btn)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    def reload(self) -> None:
        data = cfg.load()
        self.yt_enabled.setChecked(bool(data["youtube_music_enabled"]))
        self.yt_prefer.setChecked(bool(data["youtube_music_prefer"]))
        self.yt_url.setText(str(data["youtube_music_url"]))
        self.wa_toasts.setChecked(bool(data["whatsapp_toasts_enabled"]))
        self.wa_reply.setChecked(bool(data["whatsapp_reply_enabled"]))
        self.wa_uri.setText(str(data["whatsapp_uri"]))

    def _collect(self) -> dict:
        return {
            "youtube_music_enabled": self.yt_enabled.isChecked(),
            "youtube_music_prefer": self.yt_prefer.isChecked(),
            "youtube_music_url": self.yt_url.text().strip() or cfg.DEFAULTS["youtube_music_url"],
            "whatsapp_toasts_enabled": self.wa_toasts.isChecked(),
            "whatsapp_reply_enabled": self.wa_reply.isChecked(),
            "whatsapp_uri": self.wa_uri.text().strip() or cfg.DEFAULTS["whatsapp_uri"],
        }

    def _save(self) -> None:
        data = cfg.update(**self._collect())
        if self._on_changed:
            self._on_changed(data)
        QMessageBox.information(self, "Isle", "Settings saved.")

    def _open_youtube_music(self) -> None:
        url = self.yt_url.text().strip() or cfg.DEFAULTS["youtube_music_url"]
        webbrowser.open(url)

    def _open_whatsapp(self) -> None:
        uri = self.wa_uri.text().strip() or cfg.DEFAULTS["whatsapp_uri"]
        webbrowser.open(uri)

    def _open_notification_settings(self) -> None:
        """Open Windows privacy page for notification / listener access."""
        if sys.platform != "win32":
            QMessageBox.information(
                self,
                "Isle",
                "Notification access is configured in Windows Settings "
                "(Privacy → Notifications → User notification access).",
            )
            return
        # ms-settings URI for notifications privacy
        targets = (
            "ms-settings:privacy-notifications",
            "ms-settings:notifications",
        )
        for target in targets:
            try:
                os.startfile(target)  # type: ignore[attr-defined]
                return
            except OSError:
                continue
        try:
            subprocess.Popen(["explorer", "ms-settings:privacy-notifications"])
        except OSError:
            QMessageBox.warning(
                self,
                "Isle",
                "Could not open Settings. Enable User notification access under "
                "Privacy → Notifications.",
            )
