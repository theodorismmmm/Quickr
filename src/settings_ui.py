"""Tray Setup UI — wide layout with scroll so every section is reachable."""

from __future__ import annotations

import os
import sys
import webbrowser
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import isle_settings as cfg
from isle_styles import style_choices
from phone_connect import BtDevice


class SettingsWindow(QWidget):
    """Wide Setup window with a scroll area so lower sections stay accessible."""

    style_changed = Signal(str)
    phone_target_changed = Signal(str, str)

    def __init__(
        self,
        on_changed: Optional[Callable[[dict], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self.setWindowTitle("Isle Setup")
        self.setMinimumSize(760, 380)
        self.resize(900, 520)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.setStyleSheet(
            """
            QWidget { background: #121212; color: #f0f0f0; font-size: 12px; }
            QScrollArea { border: none; background: #121212; }
            QGroupBox {
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px 10px 8px 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #ffffff;
            }
            QCheckBox { spacing: 6px; }
            QLineEdit, QComboBox, QSpinBox, QListWidget {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 5px 8px;
                color: #fff;
                min-height: 22px;
            }
            QListWidget { padding: 2px; }
            QPushButton {
                background: #1c1c1c;
                border: 1px solid #3a3a3a;
                border-radius: 7px;
                padding: 6px 12px;
                color: #fff;
            }
            QPushButton:hover { border-color: #777; }
            QLabel#hint { color: #8e8e8e; font-size: 11px; }
            QLabel#title { color: #ffffff; font-size: 15px; font-weight: 600; }
            QScrollBar:vertical {
                background: #121212;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3a3a3a;
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )
        self._devices: List[BtDevice] = []
        self._refresh_bt_cb: Optional[Callable[[], None]] = None
        self._build()
        self.reload()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(14, 12, 14, 8)
        title = QLabel("Isle Setup")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        hint = QLabel("Scroll for all options · Hover expands the island · click away collapses")
        hint.setObjectName("hint")
        header_l.addWidget(title)
        header_l.addSpacing(12)
        header_l.addWidget(hint, 1)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFocusPolicy(Qt.StrongFocus)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(14, 4, 14, 14)
        body_l.setSpacing(10)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)

        # ---- Look / Timer ----
        style_box = QGroupBox("Look")
        style_form = QFormLayout(style_box)
        style_form.setSpacing(6)
        self.style_combo = QComboBox()
        for sid, label in style_choices():
            self.style_combo.addItem(label, sid)
        self.timer_mins = QSpinBox()
        self.timer_mins.setRange(1, 180)
        self.timer_mins.setSuffix(" min")
        style_form.addRow("Style", self.style_combo)
        style_form.addRow("Timer", self.timer_mins)
        left.addWidget(style_box)

        # ---- YouTube Music ----
        yt = QGroupBox("YouTube Music")
        yt_l = QVBoxLayout(yt)
        yt_l.setSpacing(6)
        self.yt_enabled = QCheckBox("Show in island")
        self.yt_prefer = QCheckBox("Prefer when multiple players are active")
        self.yt_url = QLineEdit()
        self.yt_url.setPlaceholderText("https://music.youtube.com")
        yt_row = QHBoxLayout()
        yt_row.addWidget(QLabel("URL"))
        yt_row.addWidget(self.yt_url, 1)
        open_yt = QPushButton("Open")
        open_yt.clicked.connect(self._open_youtube_music)
        yt_row.addWidget(open_yt)
        yt_l.addWidget(self.yt_enabled)
        yt_l.addWidget(self.yt_prefer)
        yt_l.addLayout(yt_row)
        left.addWidget(yt)

        # ---- WhatsApp ----
        wa = QGroupBox("WhatsApp")
        wa_l = QVBoxLayout(wa)
        wa_l.setSpacing(6)
        self.wa_toasts = QCheckBox("Show toasts in island")
        self.wa_reply = QCheckBox("Reply field (copy + open whatsapp:)")
        self.wa_uri = QLineEdit()
        self.wa_uri.setPlaceholderText("whatsapp:")
        wa_row = QHBoxLayout()
        wa_row.addWidget(QLabel("URI"))
        wa_row.addWidget(self.wa_uri, 1)
        open_wa = QPushButton("Open")
        open_wa.clicked.connect(self._open_whatsapp)
        notif = QPushButton("Notification access")
        notif.clicked.connect(self._open_notification_settings)
        wa_row.addWidget(open_wa)
        wa_row.addWidget(notif)
        wa_l.addWidget(self.wa_toasts)
        wa_l.addWidget(self.wa_reply)
        wa_l.addLayout(wa_row)
        wa_hint = QLabel("Does not send toast inline replies or automate WhatsApp Web.")
        wa_hint.setObjectName("hint")
        wa_hint.setWordWrap(True)
        wa_l.addWidget(wa_hint)
        left.addWidget(wa)
        left.addStretch(1)

        # ---- iPhone Connect ----
        phone = QGroupBox("iPhone Connect")
        phone_l = QVBoxLayout(phone)
        phone_l.setSpacing(6)
        self.phone_enabled = QCheckBox("Enable Bluetooth link")
        self.phone_status = QLabel("Bluetooth idle")
        self.phone_status.setObjectName("hint")
        self.phone_status.setWordWrap(True)
        self.phone_list = QListWidget()
        self.phone_list.setMinimumHeight(160)
        phone_l.addWidget(self.phone_enabled)
        phone_l.addWidget(self.phone_status)
        phone_l.addWidget(self.phone_list)
        phone_btns = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._request_refresh_bt)
        pick = QPushButton("Use selected")
        pick.clicked.connect(self._use_selected_phone)
        bt_settings = QPushButton("Windows Bluetooth")
        bt_settings.clicked.connect(self._open_bluetooth_settings)
        phone_btns.addWidget(refresh)
        phone_btns.addWidget(pick)
        phone_btns.addWidget(bt_settings)
        phone_btns.addStretch(1)
        phone_l.addLayout(phone_btns)
        phone_hint = QLabel(
            "Pair in Windows first. Isle tracks the BT link and shows Windows "
            "notifications in the island. Apple Continuity mirroring is not available to third-party apps."
        )
        phone_hint.setObjectName("hint")
        phone_hint.setWordWrap(True)
        phone_l.addWidget(phone_hint)
        right.addWidget(phone)
        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        body_l.addLayout(columns)
        body_l.addStretch(1)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        footer = QWidget()
        bottom = QHBoxLayout(footer)
        bottom.setContentsMargins(14, 8, 14, 12)
        bottom.addStretch(1)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(save_btn)
        bottom.addWidget(close_btn)
        outer.addWidget(footer)

    def set_bluetooth_hooks(self, refresh_cb: Callable[[], None]) -> None:
        self._refresh_bt_cb = refresh_cb

    def set_phone_status(self, text: str) -> None:
        self.phone_status.setText(text)

    def set_bluetooth_devices(self, devices: List[BtDevice]) -> None:
        self._devices = list(devices)
        current = cfg.load().get("iphone_device_address", "")
        self.phone_list.clear()
        for d in devices:
            tag = "iPhone" if d.is_iphone else "Device"
            if getattr(d, "is_connected", False):
                state = "connected"
            elif getattr(d, "is_present", False):
                state = "in range"
            else:
                state = "paired"
            item = QListWidgetItem(f"[{tag} · {state}] {d.name}")
            item.setData(Qt.UserRole, d.address)
            item.setData(Qt.UserRole + 1, d.name)
            self.phone_list.addItem(item)
            if current and (current == d.address or current.lower() in d.address.lower()):
                self.phone_list.setCurrentItem(item)

    def reload(self) -> None:
        data = cfg.load()
        idx = self.style_combo.findData(data.get("style_id"))
        self.style_combo.setCurrentIndex(max(0, idx))
        self.timer_mins.setValue(int(data.get("timer_default_minutes") or 5))
        self.yt_enabled.setChecked(bool(data["youtube_music_enabled"]))
        self.yt_prefer.setChecked(bool(data["youtube_music_prefer"]))
        self.yt_url.setText(str(data["youtube_music_url"]))
        self.wa_toasts.setChecked(bool(data["whatsapp_toasts_enabled"]))
        self.wa_reply.setChecked(bool(data["whatsapp_reply_enabled"]))
        self.wa_uri.setText(str(data["whatsapp_uri"]))
        self.phone_enabled.setChecked(bool(data.get("iphone_connect_enabled")))

    def _collect(self) -> dict:
        return {
            "style_id": self.style_combo.currentData(),
            "timer_default_minutes": int(self.timer_mins.value()),
            "youtube_music_enabled": self.yt_enabled.isChecked(),
            "youtube_music_prefer": self.yt_prefer.isChecked(),
            "youtube_music_url": self.yt_url.text().strip() or cfg.DEFAULTS["youtube_music_url"],
            "whatsapp_toasts_enabled": self.wa_toasts.isChecked(),
            "whatsapp_reply_enabled": self.wa_reply.isChecked(),
            "whatsapp_uri": self.wa_uri.text().strip() or cfg.DEFAULTS["whatsapp_uri"],
            "iphone_connect_enabled": self.phone_enabled.isChecked(),
            "iphone_device_address": cfg.load().get("iphone_device_address", ""),
            "iphone_device_name": cfg.load().get("iphone_device_name", ""),
        }

    def _save(self) -> None:
        data = self._collect()
        item = self.phone_list.currentItem()
        if item is not None:
            data["iphone_device_address"] = item.data(Qt.UserRole) or ""
            data["iphone_device_name"] = item.data(Qt.UserRole + 1) or ""
        data = cfg.update(**data)
        if self._on_changed:
            self._on_changed(data)
        self.style_changed.emit(str(data.get("style_id") or ""))
        self.phone_target_changed.emit(
            str(data.get("iphone_device_address") or ""),
            str(data.get("iphone_device_name") or ""),
        )
        QMessageBox.information(self, "Isle", "Settings saved.")

    def _use_selected_phone(self) -> None:
        item = self.phone_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Isle", "Select a Bluetooth device first.")
            return
        address = item.data(Qt.UserRole) or ""
        name = item.data(Qt.UserRole + 1) or ""
        cfg.update(
            iphone_connect_enabled=True,
            iphone_device_address=address,
            iphone_device_name=name,
        )
        self.phone_enabled.setChecked(True)
        self.phone_target_changed.emit(address, name)
        if self._on_changed:
            self._on_changed(cfg.load())
        QMessageBox.information(self, "Isle", f"Using {name} for iPhone Connect.")

    def _request_refresh_bt(self) -> None:
        if self._refresh_bt_cb:
            self._refresh_bt_cb()
        else:
            QMessageBox.information(self, "Isle", "Bluetooth service not ready yet.")

    def _open_youtube_music(self) -> None:
        webbrowser.open(self.yt_url.text().strip() or cfg.DEFAULTS["youtube_music_url"])

    def _open_whatsapp(self) -> None:
        webbrowser.open(self.wa_uri.text().strip() or cfg.DEFAULTS["whatsapp_uri"])

    def _open_notification_settings(self) -> None:
        if sys.platform != "win32":
            QMessageBox.information(self, "Isle", "Privacy → Notifications → User notification access")
            return
        for target in ("ms-settings:privacy-notifications", "ms-settings:notifications"):
            try:
                os.startfile(target)  # type: ignore[attr-defined]
                return
            except OSError:
                continue

    def _open_bluetooth_settings(self) -> None:
        if sys.platform == "win32":
            try:
                os.startfile("ms-settings:bluetooth")  # type: ignore[attr-defined]
                return
            except OSError:
                pass
        QMessageBox.information(self, "Isle", "Open Windows Settings → Bluetooth.")
