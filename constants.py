import os
import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QIcon, QFont, QColor, QPainter, QPen, QBrush

from theme import ModernTheme
import storage


# ─────────────────────────── CONSTANTS ───────────────────────────────────────
PATIENT_ASSETS_FOLDER = "patients_assets"


def canonical_exercise(name: str) -> str:
    """Normalize exercise names so 'Straight Leg Raise(s)' map to one key, etc."""
    s = (name or "").strip().lower()

    # common variations in your UI
    s = s.replace("_", " ").replace("-", " ")
    s = " ".join(s.split())

    # Map variations → a stable canonical key used in JSON
    aliases = {
        "squats": "Squats",
        "mini squats": "Squats",
        "mini-squats": "Squats",
        "seated knee bending": "Seated Knee Bending",
        "straight leg raise": "Straight Leg Raises",
        "straight leg raises": "Straight Leg Raises",
        "straight leg raising": "Straight Leg Raises",
        "initial assessment": "Initial Assessment",
        "general": "General",
    }
    return aliases.get(s, name.strip() if name else "")


# ─────────────────────────── GLOBAL DATA ──────────────────────────────────────
PATIENT_DATA_STORE = {
    "merged_info": {}, "exercise_schedule": {}, "consent": {},
    "progress": {}, "setup_videos": []
}

# "patient" or "admin" — set at login, read everywhere that needs role-gating
CURRENT_USER_ROLE = "patient"


# ─────────────────────────── SESSION MANAGER ──────────────────────────────────
class SessionManager:
    """Thin wrapper around storage module — uses per-patient folder structure."""

    @classmethod
    def save(cls, session: dict):
        info = PATIENT_DATA_STORE.get("merged_info", {})
        ok = storage.save_session(info, session)
        if not ok:
            print("SessionManager.save: storage.save_session failed")

    @classmethod
    def load(cls) -> list:
        info = PATIENT_DATA_STORE.get("merged_info", {})
        return storage.load_sessions(info)


# ─────────────────────────── ICON ─────────────────────────────────────────────
def create_app_icon():
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(ModernTheme.ACCENT_PRIMARY)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.setPen(QPen(Qt.GlobalColor.white))
    font = QFont("Segoe UI", 30, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "K")
    painter.end()
    return QIcon(pixmap)
