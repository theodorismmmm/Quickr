"""Isle visual style presets (Samsung / Xiaomi / Apple / Notch / Liquid Glass)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor


@dataclass(frozen=True)
class IsleStyle:
    id: str
    label: str
    idle: QSize
    compact: QSize
    expanded: QSize
    toast: QSize
    radius_idle: float  # 0 = full pill (half min side)
    radius_expanded: float
    fill: QColor
    fill_glass: bool
    rim: QColor
    rim_width: float
    inner: QColor
    specular: bool
    top_margin: int


STYLES: Dict[str, IsleStyle] = {
    "apple": IsleStyle(
        id="apple",
        label="Apple Dynamic Island",
        idle=QSize(126, 37),
        compact=QSize(214, 44),
        expanded=QSize(420, 220),
        toast=QSize(360, 120),
        radius_idle=0,
        radius_expanded=40,
        fill=QColor(0, 0, 0, 255),
        fill_glass=False,
        rim=QColor(255, 255, 255, 210),
        rim_width=1.4,
        inner=QColor(255, 255, 255, 40),
        specular=False,
        top_margin=8,
    ),
    "liquid_glass": IsleStyle(
        id="liquid_glass",
        label="Liquid Glass Dynamic Island",
        idle=QSize(126, 37),
        compact=QSize(214, 44),
        expanded=QSize(420, 220),
        toast=QSize(360, 120),
        radius_idle=0,
        radius_expanded=42,
        # Translucent tint — desktop must show through (no opaque black).
        fill=QColor(18, 20, 28, 110),
        fill_glass=True,
        rim=QColor(255, 255, 255, 150),
        rim_width=1.3,
        inner=QColor(255, 255, 255, 70),
        specular=True,
        top_margin=8,
    ),
    "xiaomi": IsleStyle(
        id="xiaomi",
        label="Xiaomi Dynamic Island",
        idle=QSize(118, 34),
        compact=QSize(200, 40),
        expanded=QSize(400, 210),
        toast=QSize(340, 118),
        radius_idle=0,
        radius_expanded=36,
        fill=QColor(8, 8, 10, 245),
        fill_glass=False,
        rim=QColor(255, 255, 255, 120),
        rim_width=1.0,
        inner=QColor(255, 255, 255, 28),
        specular=False,
        top_margin=10,
    ),
    "samsung_dot": IsleStyle(
        id="samsung_dot",
        label="Samsung Dot",
        idle=QSize(37, 37),
        compact=QSize(160, 40),
        expanded=QSize(380, 210),
        toast=QSize(320, 118),
        radius_idle=0,
        radius_expanded=32,
        fill=QColor(0, 0, 0, 255),
        fill_glass=False,
        rim=QColor(255, 255, 255, 180),
        rim_width=1.2,
        inner=QColor(255, 255, 255, 35),
        specular=False,
        top_margin=10,
    ),
    "notch": IsleStyle(
        id="notch",
        label="Notch",
        idle=QSize(180, 28),
        compact=QSize(240, 36),
        expanded=QSize(420, 200),
        toast=QSize(360, 110),
        radius_idle=14,
        radius_expanded=28,
        fill=QColor(0, 0, 0, 255),
        fill_glass=False,
        rim=QColor(255, 255, 255, 40),
        rim_width=1.0,
        inner=QColor(255, 255, 255, 20),
        specular=False,
        top_margin=0,
    ),
}

DEFAULT_STYLE_ID = "liquid_glass"


def get_style(style_id: str) -> IsleStyle:
    return STYLES.get(style_id) or STYLES[DEFAULT_STYLE_ID]


def style_choices() -> list[tuple[str, str]]:
    order = ("liquid_glass", "apple", "xiaomi", "samsung_dot", "notch")
    return [(sid, STYLES[sid].label) for sid in order]
