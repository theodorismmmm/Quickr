"""Tray Setup UI — styles, media, WhatsApp, iPhone Connect, timer defaults."""

from __future__ import annotations

import os
import subprocess
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import isle_settings as cfg
from isle_styles import style_choices
from phone_connect import BtDevice


class SettingsWindow(QWidget):
    """Taskbar/tray companion UI — not the island itself."""

    style_changed = Signal(str)
    phone_target_changed = Signal(str, str)  # address, name

    def __init__(
        self,
        on_changed: Optional[Callable[[dict], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self.setWindowTitle("Isle Setup")
        self.setMinimumWidth(460)
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
            QLineEdit, QComboBox, QSpinBox, QListWidget {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 6px 8px;
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
        self._devices: List[BtDevice] = []
        self._build()
        self.reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Isle Setup")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        subtitle = QLabel(
            "Always-on island over apps. Hover to expand, move away or click "
            "outside to collapse. Pick a look, connect media / WhatsApp / iPhone."
        )
        subtitle.setObjectName("hint")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        # ---- Style ----
        style_box = QGroupBox("Island style")
        style_l = QVBoxLayout(style_box)
        self.style_combo = QComboBox()
        for sid, label in style_choices():
            self.style_combo.addItem(label, sid)
        style_l.addWidget(self.style_combo)
        style_hint = QLabel(
            "Liquid Glass · Apple Dynamic Island · Xiaomi · Samsung Dot · Notch"
        )
        style_hint.setObjectName("hint")
        style_hint.setWordWrap(True)
        style_l.addWidget(style_hint)
        root.addWidget(style_box)

        # ---- Timer ----
        timer_box = QGroupBox("Timer")
        timer_l = QFormLayout(timer_box)
        self.timer_mins = QSpinBox()
        self.timer_mins.setRange(1, 180)
        self.timer_mins.setSuffix(" min")
        timer_l.addRow("Default duration", self.timer_mins)
        timer_hint = QLabel(
            "Start a timer from the tray. It shows in the island; hover to control."
        )
        timer_hint.setObjectName("hint")
        timer_hint.setWordWrap(True)
        timer_l.addRow(timer_hint)
        root.addWidget(timer_box)

        # ---- YouTube Music ----
        yt = QGroupBox("YouTube Music")
        yt_l = QVBoxLayout(yt)
        self.yt_enabled = QCheckBox("Show YouTube Music in the island")
        self.yt_prefer = QCheckBox("Prefer YouTube Music when several players are active")
        self.yt_url = QLineEdit()
        form = QFormLayout()
        form.addRow("Open URL", self.yt_url)
        yt_l.addWidget(self.yt_enabled)
        yt_l.addWidget(self.yt_prefer)
        yt_l.addLayout(form)
        open_yt = QPushButton("Open YouTube Music")
        open_yt.clicked.connect(self._open_youtube_music)
        yt_l.addWidget(open_yt, 0, Qt.AlignLeft)
        root.addWidget(yt)

        # ---- WhatsApp ----
        wa = QGroupBox("WhatsApp")
        wa_l = QVBoxLayout(wa)
        self.wa_toasts = QCheckBox("Show WhatsApp toasts in the island")
        self.wa_reply = QCheckBox("Show reply field (copies text + opens whatsapp:)")
        self.wa_uri = QLineEdit()
        wa_form = QFormLayout()
        wa_form.addRow("Launch URI", self.wa_uri)
        wa_l.addWidget(self.wa_toasts)
        wa_l.addWidget(self.wa_reply)
        wa_l.addLayout(wa_form)
        wa_hint = QLabel(
            "Reply copies text and opens WhatsApp — it does not send the toast "
            "inline reply or automate WhatsApp Web."
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

        # ---- iPhone Connect ----
        phone = QGroupBox("iPhone Connect")
        phone_l = QVBoxLayout(phone)
        self.phone_enabled = QCheckBox("Enable iPhone Connect (Bluetooth)")
        self.phone_status = QLabel("Bluetooth idle")
        self.phone_status.setObjectName("hint")
        self.phone_status.setWordWrap(True)
        self.phone_list = QListWidget()
        self.phone_list.setMinimumHeight(110)
        phone_l.addWidget(self.phone_enabled)
        phone_l.addWidget(self.phone_status)
        phone_l.addWidget(self.phone_list)
        phone_btns = QHBoxLayout()
        refresh = QPushButton("Refresh devices")
        refresh.clicked.connect(self._request_refresh_bt)
        pick = QPushButton("Use selected")
        pick.clicked.connect(self._use_selected_phone)
        bt_settings = QPushButton("Windows Bluetooth…")
        bt_settings.clicked.connect(self._open_bluetooth_settings)
        phone_btns.addWidget(refresh)
        phone_btns.addWidget(pick)
        phone_btns.addWidget(bt_settings)
        phone_btns.addStretch(1)
        phone_l.addLayout(phone_btns)
        phone_hint = QLabel(
            "Pair your iPhone in Windows first. Isle can track the Bluetooth "
            "link and show Windows notifications (WhatsApp, Mail, Phone Link, "
            "browsers, …) in the island. Apple Continuity notification mirroring "
            "is not available to third-party Windows apps."
        )
        phone_hint.setObjectName("hint")
        phone_hint.setWordWrap(True)
        phone_l.addWidget(phone_hint)
        root.addWidget(phone)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(save_btn)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        self._refresh_bt_cb: Optional[Callable[[], None]] = None

    def set_bluetooth_hooks(
        self,
        refresh_cb: Callable[[], None],
    ) -> None:
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
        # Preserve selected phone from list if present.
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
        url = self.yt_url.text().strip() or cfg.DEFAULTS["youtube_music_url"]
        webbrowser.open(url)

    def _open_whatsapp(self) -> None:
        uri = self.wa_uri.text().strip() or cfg.DEFAULTS["whatsapp_uri"]
        webbrowser.open(uri)

    def _open_notification_settings(self) -> None:
        if sys.platform != "win32":
            QMessageBox.information(
                self,
                "Isle",
                "Privacy → Notifications → User notification access",
            )
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
