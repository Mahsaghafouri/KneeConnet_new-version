import sys
import os
import json
import time
from datetime import datetime, date
from pathlib import Path

from vision_thread import CameraThread as VisionCameraThread
from voice_thread import TTSWorker
from utils import calculate_angle, get_visible_side
import storage
import reports

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QInputDialog, QDialog,
    QCheckBox, QTextEdit, QLineEdit, QFormLayout, QComboBox,
    QMessageBox, QScrollArea, QStackedWidget, QListWidget, QGroupBox,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QSpinBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QImage, QPixmap, QIcon, QFont, QColor, QPainter, QPen, QBrush, QDoubleValidator

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

import numpy as np
import subprocess
import cv2


# ─────────────────────────── THEME ────────────────────────────────────────────
class ModernTheme:
    BG_DARK = "#2b2b2b"
    BG_LIGHT = "#3b3b3b"
    ACCENT_PRIMARY = "#1abc9c"
    ACCENT_HOVER = "#16a085"
    ACCENT_DANGER = "#e74c3c"
    ACCENT_SUCCESS = "#2ecc71"
    TEXT_WHITE = "#ecf0f1"
    TEXT_GRAY = "#bdc3c7"
    BORDER_RADIUS = "8px"

    STYLESHEET = f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {BG_DARK};
            color: {TEXT_WHITE};
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
        }}
        QFrame {{
            border: none;
            border-radius: {BORDER_RADIUS};
        }}
        QFrame#Card {{
            background-color: {BG_LIGHT};
            border: 1px solid #4a4a4a;
        }}
        QPushButton {{
            background-color: {BG_LIGHT};
            border: 1px solid #555;
            padding: 8px 16px;
            border-radius: 6px;
            color: {TEXT_WHITE};
        }}
        QPushButton:hover {{
            background-color: #505050;
        }}
        QPushButton#Primary {{
            background-color: {ACCENT_PRIMARY};
            border: none;
            font-weight: bold;
            color: white;
        }}
        QPushButton#Primary:hover {{
            background-color: {ACCENT_HOVER};
        }}
        QPushButton#Danger {{
            background-color: {ACCENT_DANGER};
            border: none;
            font-weight: bold;
            color: white;
        }}
        QPushButton#Success {{
            background-color: {ACCENT_SUCCESS};
            border: none;
            font-weight: bold;
            color: white;
        }}
        QPushButton:disabled {{
            background-color: #444;
            color: #777;
        }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox {{
            background-color: #222;
            border: 1px solid #555;
            padding: 8px;
            border-radius: 4px;
            color: white;
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1px solid {ACCENT_PRIMARY};
        }}
        QListWidget {{
            background-color: {BG_LIGHT};
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            padding: 12px;
            margin: 4px;
            border-radius: 6px;
        }}
        QListWidget::item:selected {{
            background-color: {ACCENT_PRIMARY};
            color: white;
        }}
        QListWidget::item:hover {{
            background-color: #505050;
        }}
        QLabel#Header {{
            font-size: 24px;
            font-weight: bold;
            color: {ACCENT_PRIMARY};
        }}
        QLabel#SubHeader {{
            font-size: 18px;
            font-weight: bold;
            color: {TEXT_WHITE};
            margin-bottom: 10px;
        }}
        QGroupBox {{
            border: 1px solid #555;
            border-radius: 6px;
            margin-top: 1em;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 3px;
        }}
        QTableWidget {{
            background-color: #222;
            gridline-color: #555;
            border: 1px solid #555;
        }}
        QHeaderView::section {{
            background-color: {BG_LIGHT};
            padding: 5px;
            border: 1px solid #555;
        }}
    """


# ─────────────────────────── CONSTANTS ───────────────────────────────────────
PATIENT_ASSETS_FOLDER = "patients_assets"


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


# ─────────────────────────── CUSTOM LABELS ────────────────────────────────────
class HeaderLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("Header")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class SubHeaderLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("SubHeader")


# ─────────────────────────── CAMERA DISPLAY WIDGET ────────────────────────────
class CameraDisplayWidget(QWidget):
    """Stable custom-paint widget used by SetupPage."""
    def __init__(self, placeholder_text="Camera Offline"):
        super().__init__()
        self.image = None
        self.placeholder_text = placeholder_text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            f"background-color: black; border-radius: {ModernTheme.BORDER_RADIUS};"
            " border: 2px solid #555;"
        )

    def set_image(self, qt_img):
        self.image = qt_img
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        if self.image:
            scaled = self.image.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
        else:
            painter.setPen(QPen(QColor(ModernTheme.TEXT_WHITE)))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
        painter.end()


# ─────────────────────────── SIMPLE CAMERA THREAD (SetupPage only) ────────────
class SimpleCameraThread(QThread):
    """Webcam thread for SetupPage: emits frames AND live pose angles."""
    change_pixmap_signal = pyqtSignal(QImage)
    bgr_frame_signal = pyqtSignal(object)       # numpy BGR frame
    angles_signal = pyqtSignal(float, float)    # (knee_angle, hip_angle)

    def __init__(self):
        super().__init__()
        self._run_flag = True
        import mediapipe as mp
        _mp = mp.solutions.pose
        self._pose = _mp.Pose(
            static_image_mode=False,
            model_complexity=0,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp_pose = _mp
        self._mp_draw = mp.solutions.drawing_utils
        self._mp_styles = mp.solutions.drawing_styles

    def run(self):
        cap = None
        for idx, backend, label in [
            (0, cv2.CAP_DSHOW, "cam0/DSHOW"),
            (0, cv2.CAP_MSMF,  "cam0/MSMF"),
            (0, cv2.CAP_ANY,   "cam0/ANY"),
            (1, cv2.CAP_DSHOW, "cam1/DSHOW"),
            (1, cv2.CAP_ANY,   "cam1/ANY"),
        ]:
            test = cv2.VideoCapture(idx, backend)
            if test.isOpened():
                cap = test
                print(f"SetupPage camera: {label}")
                break
            test.release()

        if cap is None:
            print("SetupPage: no camera found")
            return

        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                bgr_copy = cv_img.copy()
                self.bgr_frame_signal.emit(bgr_copy)

                rgb = cv2.cvtColor(bgr_copy, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = self._pose.process(rgb)
                rgb.flags.writeable = True

                knee_angle = hip_angle = 0.0
                if results and results.pose_landmarks:
                    lm = results.pose_landmarks.landmark
                    side = get_visible_side(lm)
                    s = lm[side["shoulder"]]
                    h_lm = lm[side["hip"]]
                    k = lm[side["knee"]]
                    a = lm[side["ankle"]]
                    knee_angle = float(calculate_angle(
                        [h_lm.x, h_lm.y], [k.x, k.y], [a.x, a.y]
                    ))
                    hip_angle = float(calculate_angle(
                        [s.x, s.y], [h_lm.x, h_lm.y], [k.x, k.y]
                    ))
                    self.angles_signal.emit(knee_angle, hip_angle)

                    # Draw skeleton overlay
                    self._mp_draw.draw_landmarks(
                        rgb, results.pose_landmarks,
                        self._mp_pose.POSE_CONNECTIONS,
                        self._mp_styles.get_default_pose_landmarks_style(),
                    )
                    # Draw angle values on frame
                    h_img, w_img = rgb.shape[:2]
                    kx = int(k.x * w_img)
                    ky = int(k.y * h_img)
                    hx = int(h_lm.x * w_img)
                    hy = int(h_lm.y * h_img)
                    cv2.putText(rgb, f"Knee:{int(knee_angle)}", (kx - 80, ky - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 128), 2, cv2.LINE_AA)
                    cv2.putText(rgb, f"Hip:{int(hip_angle)}", (hx + 10, hy),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)

                h_img, w_img, ch = rgb.shape
                qt_img = QImage(rgb.data, w_img, h_img, ch * w_img, QImage.Format.Format_RGB888)
                self.change_pixmap_signal.emit(qt_img.copy())
            else:
                self.msleep(100)
        cap.release()

    def stop(self):
        self._run_flag = False
        self.wait(1000)


# ─────────────────────────── TERMS DIALOG ────────────────────────────────────
class TermsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Welcome to Knee Connect")
        self.setWindowIcon(create_app_icon())
        self.setFixedSize(600, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        layout.addWidget(HeaderLabel("Welcome to KneeConnect"))
        subtitle = QLabel("Clinical Use Notice & Terms")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #bdc3c7; font-size: 14px; margin-top: -8px; border: none;")
        layout.addWidget(subtitle)

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFrameShape(QFrame.Shape.NoFrame)
        self.text_area.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; padding: 10px; border-radius: 8px;"
        )
        last_updated = date.today().strftime("%Y-%m-%d")
        self.text_area.setHtml(f"""
<h2 style="margin:0; padding:0;">KneeConnect — Clinical Use Notice &amp; Terms</h2>
<p style="margin-top:6px; color:#bdc3c7;">
<b>Last Updated:</b> {last_updated}
</p>
<hr style="border:0; border-top:1px solid #555; margin:12px 0;">

<h3>1) Authorized Use</h3>
<p>
This software is intended for use by authorized clinicians, physiotherapists, and trained staff.
</p>

<h3>2) Patient Data &amp; Privacy</h3>
<p>
Patient data entered in the application may be saved locally (e.g., JSON records). You are responsible for ensuring
compliance with applicable privacy laws (e.g., GDPR/HIPAA) when storing, exporting, or sharing data.
</p>

<h3>3) Clinical Disclaimer</h3>
<p>
KneeConnect provides computer-vision assisted metrics and exercise guidance. It is an assistive tool and does not replace
clinical judgement. Always verify measurements and patient safety before prescribing or continuing exercises.
</p>

<h3>4) Safety</h3>
<p>
Stop the session immediately if the patient experiences pain, dizziness, or instability. Ensure the environment is safe and
the patient is supervised when required.
</p>

<h3>5) Liability</h3>
<p>
The developers are not liable for injury, misuse, or misinterpretation of results. Use is at the clinician's discretion.
</p>

<br>
<p style="color:#bdc3c7;"><i>Check the box below to confirm you understand and agree.</i></p>
""")
        layout.addWidget(self.text_area)

        chk_layout = QHBoxLayout()
        self.chk_agree = QCheckBox("I have read and agree to the Terms & Conditions")
        self.chk_agree.setStyleSheet("font-size: 16px; spacing: 10px;")
        self.chk_agree.stateChanged.connect(self._toggle_button)
        chk_layout.addStretch()
        chk_layout.addWidget(self.chk_agree)
        chk_layout.addStretch()
        layout.addLayout(chk_layout)

        self.btn_proceed = QPushButton("ENTER APPLICATION")
        self.btn_proceed.setFixedSize(200, 50)
        self.btn_proceed.setEnabled(False)
        self.btn_proceed.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.btn_proceed.clicked.connect(self.accept)
        self.btn_proceed.setStyleSheet("background-color: #555; color: #888; border: none; border-radius: 25px;")

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_proceed)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _toggle_button(self):
        if self.chk_agree.isChecked():
            self.btn_proceed.setEnabled(True)
            self.btn_proceed.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_proceed.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_PRIMARY}; color: white; "
                "border-radius: 25px; font-weight: bold; font-size: 16px;"
            )
        else:
            self.btn_proceed.setEnabled(False)
            self.btn_proceed.setCursor(Qt.CursorShape.ForbiddenCursor)
            self.btn_proceed.setStyleSheet(
                "background-color: #555; color: #888; border: none; border-radius: 25px;"
            )


# ─────────────────────────── PATIENT INFO FORM ───────────────────────────────
class MergedPatientForm(QWidget):
    def __init__(self):
        super().__init__()
        self._locked = False   # True = view-only mode, False = edit mode
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Action bar (always visible above the form) ──────────────────────
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 0, 0, 4)
        self._lbl_mode = QLabel("New Patient")
        self._lbl_mode.setStyleSheet(
            "color: #2ecc71; font-size: 11px; font-weight: bold; border: none;"
        )
        action_bar.addWidget(self._lbl_mode)
        action_bar.addStretch()
        self._btn_edit_toggle = QPushButton("✎  Edit Information")
        self._btn_edit_toggle.setObjectName("Primary")
        self._btn_edit_toggle.setFixedHeight(32)
        self._btn_edit_toggle.setVisible(False)   # shown only when a patient is loaded
        self._btn_edit_toggle.clicked.connect(self._toggle_edit_mode)
        action_bar.addWidget(self._btn_edit_toggle)
        layout.addLayout(action_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        main_form_layout = QVBoxLayout(content)

        main_form_layout.addWidget(SubHeaderLabel("Appointment & Patient Identity"))

        grid = QGridLayout()
        grid.setSpacing(15)

        grid.addWidget(QLabel("First Name:"), 0, 0)
        self.fname = QLineEdit()
        self.fname.editingFinished.connect(self.check_existing_patient)
        grid.addWidget(self.fname, 0, 1)

        grid.addWidget(QLabel("Last Name:"), 0, 2)
        self.lname = QLineEdit()
        self.lname.editingFinished.connect(self.check_existing_patient)
        grid.addWidget(self.lname, 0, 3)

        grid.addWidget(QLabel("Patient ID:"), 1, 0)
        self.pid = QLineEdit()
        grid.addWidget(self.pid, 1, 1)

        grid.addWidget(QLabel("Age:"), 1, 2)
        self.age = QLineEdit()
        self.age.setFixedWidth(60)
        self.age.setPlaceholderText("##")
        grid.addWidget(self.age, 1, 3, Qt.AlignmentFlag.AlignLeft)

        grid.addWidget(QLabel("Mobile:"), 2, 0)
        self.mobile = QLineEdit()
        grid.addWidget(self.mobile, 2, 1)

        grid.addWidget(QLabel("Gender:"), 2, 2)
        self.gender = QComboBox()
        self.gender.addItems(["Male", "Female", "Other"])
        grid.addWidget(self.gender, 2, 3)

        main_form_layout.addLayout(grid)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #555;")
        main_form_layout.addWidget(sep)

        main_form_layout.addWidget(SubHeaderLabel("Clinical Information"))

        grid2 = QGridLayout()
        grid2.setSpacing(15)

        grid2.addWidget(QLabel("Surgeon:"), 0, 0)
        self.surgeon = QLineEdit()
        grid2.addWidget(self.surgeon, 0, 1)

        grid2.addWidget(QLabel("Physiotherapist:"), 0, 2)
        self.physio = QLineEdit()
        grid2.addWidget(self.physio, 0, 3)

        grid2.addWidget(QLabel("Height (cm):"), 1, 0)
        self.height = QLineEdit()
        self.height.setFixedWidth(80)
        grid2.addWidget(self.height, 1, 1, Qt.AlignmentFlag.AlignLeft)

        grid2.addWidget(QLabel("Weight (kg):"), 1, 2)
        self.weight = QLineEdit()
        self.weight.setFixedWidth(80)
        grid2.addWidget(self.weight, 1, 3, Qt.AlignmentFlag.AlignLeft)

        main_form_layout.addLayout(grid2)

        main_form_layout.addWidget(QLabel("Type of Surgery and Date:"))
        self.surgery_date = QLineEdit()
        main_form_layout.addWidget(self.surgery_date)

        main_form_layout.addWidget(QLabel("Nutritional Factors Affecting Healing:"))
        self.nutrition = QTextEdit()
        self.nutrition.setMaximumHeight(80)
        main_form_layout.addWidget(self.nutrition)

        main_form_layout.addWidget(QLabel("Functional Goals:"))
        self.func_goals = QTextEdit()
        self.func_goals.setMaximumHeight(80)
        main_form_layout.addWidget(self.func_goals)

        main_form_layout.addWidget(QLabel("Medical History:"))
        self.history = QTextEdit()
        self.history.setMaximumHeight(80)
        main_form_layout.addWidget(self.history)

        main_form_layout.addWidget(QLabel("Current Medication:"))
        self.meds = QTextEdit()
        self.meds.setMaximumHeight(80)
        main_form_layout.addWidget(self.meds)

        btn_save = QPushButton("Save Patient Record")
        btn_save.setObjectName("Primary")
        btn_save.clicked.connect(self.save_data)
        main_form_layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignRight)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _all_editable_fields(self):
        return [
            self.pid, self.age, self.mobile, self.surgeon, self.physio,
            self.height, self.weight, self.surgery_date,
            self.nutrition, self.func_goals, self.history, self.meds,
        ]

    # ── Edit / View mode helpers ──────────────────────────────────────────────
    def _set_locked(self, locked: bool):
        """Lock (view-only) or unlock (edit) all form fields."""
        self._locked = locked
        ro_style = (
            "color: #ccc; background-color: #1e1e1e; "
            "border: 1px solid #3a3a3a; border-radius: 4px;"
        )
        edit_style = ""   # let stylesheet cascade handle normal edit fields
        for w in self._all_editable_fields():
            if isinstance(w, QLineEdit):
                w.setReadOnly(locked)
                w.setStyleSheet(ro_style if locked else edit_style)
            elif isinstance(w, QTextEdit):
                w.setReadOnly(locked)
                w.setStyleSheet(ro_style if locked else edit_style)
        self.fname.setReadOnly(locked)
        self.fname.setStyleSheet(ro_style if locked else edit_style)
        self.lname.setReadOnly(locked)
        self.lname.setStyleSheet(ro_style if locked else edit_style)
        self.gender.setEnabled(not locked)
        if locked:
            self._btn_edit_toggle.setText("✎  Edit Information")
            self._btn_edit_toggle.setObjectName("Primary")
            self._lbl_mode.setText("Viewing patient record")
            self._lbl_mode.setStyleSheet(
                "color: #bdc3c7; font-size: 11px; border: none;"
            )
        else:
            self._btn_edit_toggle.setText("✕  Cancel Editing")
            self._btn_edit_toggle.setObjectName("")
            self._lbl_mode.setText("Editing — unsaved changes")
            self._lbl_mode.setStyleSheet(
                "color: #f39c12; font-size: 11px; font-weight: bold; border: none;"
            )
        # force Qt to re-polish the toggle button after objectName change
        self._btn_edit_toggle.style().unpolish(self._btn_edit_toggle)
        self._btn_edit_toggle.style().polish(self._btn_edit_toggle)

    def _toggle_edit_mode(self):
        """Switch between view-only and edit mode."""
        self._set_locked(not self._locked)

    def load_patient(self, data: dict):
        """Populate all form fields from an existing patient data dict and lock for viewing."""
        name_parts = data.get("name", "").split(" ", 1)
        self.fname.setText(name_parts[0] if name_parts else "")
        self.lname.setText(name_parts[1] if len(name_parts) > 1 else "")
        self.pid.setText(str(data.get("id", "")))
        self.age.setText(str(data.get("age", "")))
        self.mobile.setText(str(data.get("mobile", "")))
        idx = self.gender.findText(data.get("gender", "Male"))
        self.gender.setCurrentIndex(idx if idx >= 0 else 0)
        self.surgeon.setText(str(data.get("surgeon", "")))
        self.physio.setText(str(data.get("physio", "")))
        self.height.setText(str(data.get("height", "")))
        self.weight.setText(str(data.get("weight", "")))
        self.surgery_date.setText(str(data.get("surgery_date", "")))
        self.nutrition.setPlainText(str(data.get("nutrition", "")))
        self.func_goals.setPlainText(str(data.get("goals", "")))
        self.history.setPlainText(str(data.get("history", "")))
        self.meds.setPlainText(str(data.get("meds", "")))
        # Lock into view-only mode; show the Edit toggle
        self._set_locked(True)
        self._btn_edit_toggle.setVisible(True)

    def check_existing_patient(self):
        f_txt = self.fname.text().strip()
        l_txt = self.lname.text().strip()
        if not f_txt or not l_txt:
            return
        filename = f"{f_txt}_{l_txt}.json"
        if os.path.exists(filename):
            try:
                with open(filename, "r") as fh:
                    data = json.load(fh)
                self.pid.setText(data.get("id", ""))
                self.age.setText(data.get("age", ""))
                self.mobile.setText(data.get("mobile", ""))
                self.gender.setCurrentText(data.get("gender", "Male"))
                self.surgeon.setText(data.get("surgeon", ""))
                self.physio.setText(data.get("physio", ""))
                self.height.setText(data.get("height", ""))
                self.weight.setText(data.get("weight", ""))
                self.surgery_date.setText(data.get("surgery_date", ""))
                self.nutrition.setText(data.get("nutrition", ""))
                self.func_goals.setText(data.get("goals", ""))
                self.history.setText(data.get("history", ""))
                self.meds.setText(data.get("meds", ""))
                self._set_locked(True)
                self._btn_edit_toggle.setVisible(True)
            except Exception as e:
                print(f"Error loading patient file: {e}")

    def save_data(self):
        f_txt = self.fname.text().strip()
        l_txt = self.lname.text().strip()
        if not f_txt or not l_txt:
            QMessageBox.warning(self, "Error", "First and Last Name are required to save.")
            return
        data = {
            "name": f"{f_txt} {l_txt}",
            "id": self.pid.text(),
            "age": self.age.text(),
            "mobile": self.mobile.text(),
            "gender": self.gender.currentText(),
            "surgeon": self.surgeon.text(),
            "physio": self.physio.text(),
            "height": self.height.text(),
            "weight": self.weight.text(),
            "surgery_date": self.surgery_date.text(),
            "nutrition": self.nutrition.toPlainText(),
            "goals": self.func_goals.toPlainText(),
            "history": self.history.toPlainText(),
            "meds": self.meds.toPlainText(),
        }
        PATIENT_DATA_STORE["merged_info"] = data
        filename = f"{f_txt}_{l_txt}.json"
        try:
            with open(filename, "w") as fh:
                json.dump(data, fh, indent=4)
            QMessageBox.information(self, "Saved", f"Patient record saved.")
            self._set_locked(True)
            self._btn_edit_toggle.setVisible(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")
            return

        # Also save to patient assets folder, preserving existing videos/thresholds
        pid = self.pid.text().strip()
        folder_id = pid if pid else f"{f_txt}_{l_txt}"
        assets_dir = Path(PATIENT_ASSETS_FOLDER) / folder_id
        assets_dir.mkdir(parents=True, exist_ok=True)
        pat_json = assets_dir / "patient.json"
        existing: dict = {}
        if pat_json.exists():
            try:
                with open(pat_json) as fh:
                    existing = json.load(fh)
            except Exception:
                pass
        merged = {**existing, **data}  # patient info overwrites, videos/thresholds preserved
        try:
            with open(pat_json, "w") as fh:
                json.dump(merged, fh, indent=2)
        except Exception as e:
            print(f"Could not save to assets folder: {e}")


# ─────────────────────────── SETUP / VIDEO PAGE ───────────────────────────────
class VideoSlotWidget(QFrame):
    """A card showing a recorded video thumbnail with play, model, and delete buttons."""
    deleted = pyqtSignal(object)        # emits self
    model_selected = pyqtSignal(object) # emits self when ★ is clicked

    def __init__(self, index, video_path=None, thumb_path=None, label=""):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedSize(175, 178)
        self.video_path = video_path
        self.thumb_path = thumb_path
        self.slot_index = index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # Thumbnail
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(160, 95)
        self.thumb_lbl.setStyleSheet("background-color: #111; border-radius: 4px;")
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_thumb()
        layout.addWidget(self.thumb_lbl)

        # Label
        display = label or f"Video {index}"
        if len(display) > 20:
            display = display[:17] + "..."
        self.name_lbl = QLabel(display)
        self.name_lbl.setStyleSheet("color: #bdc3c7; font-size: 10px; border: none;")
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_lbl)

        # Top buttons: play + delete
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)

        if video_path and Path(video_path).exists():
            btn_play = QPushButton("▶ Play")
            btn_play.setFixedHeight(22)
            btn_play.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_PRIMARY}; color: white; "
                "font-size: 10px; border-radius: 3px; padding: 0 4px;"
            )
            btn_play.clicked.connect(self._play)
            btn_row.addWidget(btn_play)

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(28, 22)
        btn_del.setStyleSheet(
            f"background-color: {ModernTheme.ACCENT_DANGER}; color: white; "
            "font-size: 10px; border-radius: 3px;"
        )
        btn_del.setToolTip("Remove from list")
        btn_del.clicked.connect(lambda: self.deleted.emit(self))
        btn_row.addWidget(btn_del)
        layout.addLayout(btn_row)

        # Model button (full-width, togglable)
        self.btn_model = QPushButton("☆  Set as Patient Model")
        self.btn_model.setFixedHeight(22)
        self.btn_model.setStyleSheet(
            "background-color: #444; color: #aaa; font-size: 9px; border-radius: 3px;"
        )
        self.btn_model.setToolTip("Show this video to the patient during exercise")
        self.btn_model.clicked.connect(lambda: self.model_selected.emit(self))
        layout.addWidget(self.btn_model)

    def set_as_model(self, is_model: bool):
        if is_model:
            self.btn_model.setText("★  Patient Model  ★")
            self.btn_model.setStyleSheet(
                "background-color: #f1c40f; color: #1a1a00; "
                "font-size: 9px; font-weight: bold; border-radius: 3px;"
            )
        else:
            self.btn_model.setText("☆  Set as Patient Model")
            self.btn_model.setStyleSheet(
                "background-color: #444; color: #aaa; font-size: 9px; border-radius: 3px;"
            )

    def _load_thumb(self):
        if self.thumb_path and Path(self.thumb_path).exists():
            pix = QPixmap(str(self.thumb_path)).scaled(
                160, 95,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumb_lbl.setPixmap(pix)
        else:
            self.thumb_lbl.setText(f"Slot {self.slot_index}")

    def _play(self):
        if self.video_path and Path(self.video_path).exists():
            try:
                os.startfile(str(Path(self.video_path).resolve()))
            except Exception as e:
                print(f"Cannot open video: {e}")


class SetupPage(QWidget):
    """Patient setup page: record MP4 videos, manage thresholds, view thumbnails."""

    def __init__(self):
        super().__init__()
        self.video_slots: list[VideoSlotWidget] = []
        self.recording = False
        self.current_frame_bgr = None
        self._video_writer = None
        self._recording_path: str | None = None
        self._thumb_path: str | None = None
        self._record_frame_count = 0
        self.thread: SimpleCameraThread | None = None
        # Angle tracking during recording
        self._knee_samples: list[float] = []
        self._hip_samples: list[float] = []
        self._last_knee = 0.0
        self._last_hip = 0.0

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        # ─── LEFT PANEL: patient info + video list ───
        left_panel = QWidget()
        left_panel.setFixedWidth(240)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        pat_grp = QGroupBox("Current Patient")
        pat_gl = QVBoxLayout(pat_grp)
        pat_gl.setContentsMargins(8, 4, 8, 8)
        self.lbl_patient = QLabel("No patient selected")
        self.lbl_patient.setStyleSheet("color: #bdc3c7; font-size: 11px; border: none;")
        self.lbl_patient.setWordWrap(True)
        pat_gl.addWidget(self.lbl_patient)
        left_layout.addWidget(pat_grp)

        left_layout.addWidget(SubHeaderLabel("Recorded Videos"))

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.video_container = QWidget()
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.setSpacing(8)
        self.video_layout.addStretch()
        self.scroll_area.setWidget(self.video_container)
        left_layout.addWidget(self.scroll_area)

        main_layout.addWidget(left_panel)

        # ─── CENTER PANEL: camera + recording + thresholds ───
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        # ── Status / warning banner ─────────────────────────────────────────
        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setStyleSheet(
            "background-color: #2c3e50; color: #f39c12; font-size: 11px; "
            "border: 1px solid #f39c12; border-radius: 4px; padding: 4px 8px;"
        )
        self._banner.setVisible(False)
        center_layout.addWidget(self._banner)

        # Method / protocol selection
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Method:"))
        self.combo_method = QComboBox()
        self.combo_method.addItems([
            "Option 1 (Standard)",
            "Option 2 (Advanced)",
            "Option 3 (Custom)",
        ])
        self.combo_method.setMinimumWidth(180)
        method_row.addWidget(self.combo_method)
        method_row.addStretch()
        center_layout.addLayout(method_row)

        lbl_row = QHBoxLayout()
        lbl_row.addWidget(QLabel("Recording label:"))
        self.combo_exercise_label = QComboBox()
        self.combo_exercise_label.addItems([
            "General", "Squats", "Seated Knee Bending",
            "Straight Leg Raises", "Initial Assessment",
        ])
        lbl_row.addWidget(self.combo_exercise_label)
        lbl_row.addStretch()
        center_layout.addLayout(lbl_row)

        # Camera — must dominate vertical space
        self.cam_frame = CameraDisplayWidget("Camera Offline")
        self.cam_frame.setMinimumHeight(320)
        # Expanding policy is already set inside CameraDisplayWidget, but be explicit here
        self.cam_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        center_layout.addWidget(self.cam_frame, stretch=1)

        # Live angle display — compact bar, capped height so it never steals camera space
        angle_bar = QFrame()
        angle_bar.setMaximumHeight(52)
        angle_bar_layout = QHBoxLayout(angle_bar)
        angle_bar_layout.setContentsMargins(4, 2, 4, 2)
        angle_bar_layout.setSpacing(20)
        title_s = f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        val_s = (f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 15px; "
                 "font-weight: bold; border: none;")
        for attr, title in [("lbl_setup_knee", "KNEE ANGLE (°)"),
                             ("lbl_setup_hip",  "HIP ANGLE (°)")]:
            col = QVBoxLayout()
            col.setSpacing(1)
            t = QLabel(title)
            t.setStyleSheet(title_s)
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel("—")
            v.setStyleSheet(val_s)
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(t)
            col.addWidget(v)
            setattr(self, attr, v)
            angle_bar_layout.addLayout(col)
        center_layout.addWidget(angle_bar)

        rec_row = QHBoxLayout()
        self.btn_rec = QPushButton("⏺  START RECORDING")
        self.btn_rec.setObjectName("Success")
        self.btn_rec.setFixedHeight(40)
        self.btn_rec.clicked.connect(self.toggle_recording)
        rec_row.addWidget(self.btn_rec)
        btn_add_file = QPushButton("📂  Add from File")
        btn_add_file.setFixedHeight(40)
        btn_add_file.setToolTip("Browse for an existing MP4 video to add as a video slot")
        btn_add_file.clicked.connect(self._add_video_from_file)
        rec_row.addWidget(btn_add_file)
        self.lbl_rec_status = QLabel("")
        self.lbl_rec_status.setStyleSheet(
            "color: #e74c3c; font-weight: bold; border: none;"
        )
        self.lbl_rec_status.setMinimumWidth(120)
        rec_row.addWidget(self.lbl_rec_status)
        center_layout.addLayout(rec_row)

        # ── Bottom controls: thresholds + angle targets + save
        # Wrapped in a capped scroll area so they never compete with the camera
        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(6)

        # Thresholds
        thresh_grp = QGroupBox("Exercise Thresholds")
        thresh_gl = QGridLayout(thresh_grp)
        thresh_gl.setSpacing(4)
        thresh_gl.setContentsMargins(8, 4, 8, 6)
        self.thresh_inputs: dict[str, QLineEdit] = {}
        thresholds = [
            ("Squats – knee-down angle (°)",    "squat_knee_down",  "90"),
            ("Squats – knee-forward threshold", "squat_knee_fwd",   "0.05"),
            ("Seated Bend – extension (°)",     "seated_ext",       "160"),
            ("Seated Bend – flexion (°)",       "seated_flex",      "90"),
            ("Leg Raise – min hip angle (°)",   "slr_min_hip",      "140"),
        ]
        for row, (lbl_txt, key, default) in enumerate(thresholds):
            thresh_gl.addWidget(QLabel(lbl_txt), row, 0)
            inp = QLineEdit(default)
            inp.setFixedWidth(65)
            inp.setValidator(QDoubleValidator(0.0, 360.0, 2))
            thresh_gl.addWidget(inp, row, 1, Qt.AlignmentFlag.AlignLeft)
            self.thresh_inputs[key] = inp
        btn_save_thresh = QPushButton("Save Thresholds")
        btn_save_thresh.setFixedHeight(28)
        btn_save_thresh.clicked.connect(self._save_thresholds)
        thresh_gl.addWidget(btn_save_thresh, len(thresholds), 0, 1, 2)
        ctrl_layout.addWidget(thresh_grp)

        # Angle targets
        angle_tgt_grp = QGroupBox("Angle Targets (°)")
        atg_gl = QGridLayout(angle_tgt_grp)
        atg_gl.setSpacing(4)
        atg_gl.setContentsMargins(8, 4, 8, 6)
        self.angle_inputs: dict[str, QLineEdit] = {}
        for col, (key, lbl_txt) in enumerate([
            ("angle1", "Target 1"), ("angle2", "Target 2"),
            ("angle3", "Target 3"), ("angle4", "Target 4"),
        ]):
            atg_gl.addWidget(QLabel(lbl_txt), 0, col)
            inp = QLineEdit("0")
            inp.setFixedWidth(55)
            inp.setValidator(QDoubleValidator(0.0, 360.0, 2))
            atg_gl.addWidget(inp, 1, col)
            self.angle_inputs[key] = inp
        ctrl_layout.addWidget(angle_tgt_grp)

        # Save Setup button
        btn_save_setup = QPushButton("💾  Save Setup")
        btn_save_setup.setObjectName("Primary")
        btn_save_setup.setFixedHeight(34)
        btn_save_setup.clicked.connect(self._save_setup_full)
        ctrl_layout.addWidget(btn_save_setup)

        # Scroll area caps the controls block — camera never loses its space
        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidget(ctrl_widget)
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setMaximumHeight(160)
        ctrl_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        center_layout.addWidget(ctrl_scroll)

        main_layout.addWidget(center_widget, stretch=1)

    # ── Patient helpers ──────────────────────────────────────────────────────
    def _get_pid(self):
        """Return the patient folder key.

        Priority:
          1. Patient ID if set  (e.g. "PT-001")
          2. Name-based key     (e.g. "Jane_Doe")  — matches save_data() folder logic
          3. None               — truly unknown patient, block disk operations
        """
        info = PATIENT_DATA_STORE.get("merged_info", {})
        pid = info.get("id", "").strip()
        if pid:
            return pid
        name = info.get("name", "").strip()
        if name:
            return name.replace(" ", "_")
        return None

    def _has_real_id(self) -> bool:
        """True only when patient has an explicit ID (not a name-based fallback)."""
        info = PATIENT_DATA_STORE.get("merged_info", {})
        return bool(info.get("id", "").strip())

    def refresh_patient(self):
        """Update patient label, banner, and reload video list + setup data.

        Works for:
          • New patient   — filled form not yet saved (uses name as folder key)
          • Saved patient — loaded from browser (uses patient ID as folder key)
          • No patient    — shows placeholder, banner prompts admin to fill the profile
        """
        info = PATIENT_DATA_STORE.get("merged_info", {})
        name = info.get("name", "")
        pid  = info.get("id", "")

        # ── Patient label ─────────────────────────────────────────────────────
        parts = []
        if name:
            parts.append(name)
        if pid:
            parts.append(f"ID: {pid}")
        self.lbl_patient.setText("\n".join(parts) if parts else "No patient selected")

        # ── Status banner ─────────────────────────────────────────────────────
        folder_pid = self._get_pid()
        if not folder_pid:
            self._banner.setText(
                "⚠  No patient loaded. Fill in the Patient Profile tab and save it first."
            )
            self._banner.setVisible(True)
        elif not self._has_real_id():
            self._banner.setText(
                f"⚠  No Patient ID set — data saved under '{folder_pid}'. "
                "Set an ID in Patient Profile for permanent records."
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        # ── Load existing data ────────────────────────────────────────────────
        self._load_existing_videos(folder_pid)   # shows placeholder if None
        if folder_pid:
            self._load_thresholds(folder_pid)
            self._load_setup_data(folder_pid)

    def _load_existing_videos(self, pid):
        for slot in self.video_slots:
            slot.deleteLater()
        self.video_slots.clear()

        # Remove any previous placeholder label
        for i in range(self.video_layout.count() - 1, -1, -1):
            item = self.video_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QLabel) and w.objectName() == "NoVideosPlaceholder":
                self.video_layout.removeWidget(w)
                w.deleteLater()

        if not pid:
            lbl = QLabel("No setup videos yet.\nUse ⏺ START RECORDING to add one.")
            lbl.setObjectName("NoVideosPlaceholder")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
            )
            self.video_layout.insertWidget(0, lbl)
            return

        loaded_from_json = False
        model_path = ""
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
                model_path = data.get("model_video", {}).get("path", "")
                # Prefer setup.videos (new format); fall back to top-level videos
                videos_list = data.get("setup", {}).get("videos") or data.get("videos", [])
                for i, v in enumerate(videos_list):
                    vpath = v.get("path", "")
                    tpath = v.get("thumb", "")
                    label = v.get("exercise", f"Video {i + 1}")
                    if Path(vpath).exists():
                        slot = VideoSlotWidget(
                            i + 1, vpath,
                            tpath if Path(tpath).exists() else None,
                            label,
                        )
                        slot._angle_meta = v.get("angles", {})
                        slot._created_at = v.get("created_at", "")
                        slot._notes = v.get("notes", "")
                        slot.deleted.connect(self._remove_video_slot)
                        slot.model_selected.connect(self._on_model_selected)
                        slot.set_as_model(str(vpath) == model_path)
                        self.video_layout.insertWidget(
                            self.video_layout.count() - 1, slot
                        )
                        self.video_slots.append(slot)
                loaded_from_json = True
            except Exception as e:
                print(f"_load_existing_videos error: {e}")
                loaded_from_json = False

        if not loaded_from_json:
            # Fallback: scan directory
            vid_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "videos"
            thumb_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "thumbs"
            if vid_dir.exists():
                for i, vid_file in enumerate(sorted(vid_dir.glob("*.mp4"))):
                    thumb_path = thumb_dir / f"{vid_file.stem}.jpg"
                    slot = VideoSlotWidget(
                        i + 1, str(vid_file),
                        str(thumb_path) if thumb_path.exists() else None,
                        vid_file.stem[:20],
                    )
                    slot._angle_meta = {}
                    slot.deleted.connect(self._remove_video_slot)
                    slot.model_selected.connect(self._on_model_selected)
                    self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
                    self.video_slots.append(slot)

        if not self.video_slots:
            lbl = QLabel("No setup videos yet.\nUse ⏺ START RECORDING to add one.")
            lbl.setObjectName("NoVideosPlaceholder")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
            )
            self.video_layout.insertWidget(0, lbl)

    def _load_thresholds(self, pid: str):
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        if not json_path.exists():
            return
        try:
            with open(json_path) as f:
                data = json.load(f)
            for key, inp in self.thresh_inputs.items():
                val = data.get("thresholds", {}).get(key)
                if val is not None:
                    inp.setText(str(val))
        except Exception:
            pass

    def _remove_video_slot(self, slot: "VideoSlotWidget"):
        if slot in self.video_slots:
            self.video_slots.remove(slot)
        slot.deleteLater()
        self._persist_video_metadata()

    def _persist_video_metadata(self):
        pid = self._get_pid()
        if not pid:
            return
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        data: dict = {}
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
            except Exception:
                pass
        data["videos"] = [
            {
                "path": str(s.video_path),
                "thumb": str(s.thumb_path) if s.thumb_path else "",
                "exercise": s.name_lbl.text(),
                "angles": getattr(s, "_angle_meta", {}),
            }
            for s in self.video_slots if s.video_path
        ]
        json_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"_persist_video_metadata error: {e}")

    def _save_thresholds(self):
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(self, "No Patient",
                                "No patient loaded. Please fill in the Patient Profile tab first.")
            return
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        data: dict = {}
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
            except Exception:
                pass
        thresholds = {}
        for key, inp in self.thresh_inputs.items():
            try:
                thresholds[key] = float(inp.text())
            except ValueError:
                pass
        data["thresholds"] = thresholds
        json_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Saved", "Thresholds saved to patient record.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save thresholds: {e}")

    def _save_setup_full(self):
        """Save method, angle_targets, thresholds, and video list to patient JSON."""
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(self, "No Patient",
                                "No patient loaded. Please fill in the Patient Profile tab first.")
            return
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        data: dict = {}
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
            except Exception:
                pass

        # Build the setup block
        videos_payload = [
            {
                "exercise":   s.name_lbl.text(),
                "path":       str(s.video_path),
                "thumb":      str(s.thumb_path) if s.thumb_path else "",
                "created_at": getattr(s, "_created_at", ""),
                "notes":      getattr(s, "_notes", ""),
                "angles":     getattr(s, "_angle_meta", {}),
            }
            for s in self.video_slots if s.video_path
        ]
        angle_targets = {}
        for key, inp in self.angle_inputs.items():
            try:
                angle_targets[key] = float(inp.text())
            except ValueError:
                angle_targets[key] = 0.0

        data["setup"] = {
            "method":        self.combo_method.currentText(),
            "videos":        videos_payload,
            "angle_targets": angle_targets,
        }
        # Keep top-level videos in sync for backward compat (exercise screen reads it)
        data["videos"] = videos_payload
        # Save thresholds alongside
        thresholds = {}
        for key, inp in self.thresh_inputs.items():
            try:
                thresholds[key] = float(inp.text())
            except ValueError:
                pass
        if thresholds:
            data["thresholds"] = thresholds

        json_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Saved", "Setup saved to patient record.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save setup: {e}")

    def _load_setup_data(self, pid: str):
        """Load method and angle_targets from patient JSON into the UI."""
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        if not json_path.exists():
            return
        try:
            with open(json_path) as f:
                data = json.load(f)
            setup = data.get("setup", {})
            # Method
            method = setup.get("method", "Option 1 (Standard)")
            idx = self.combo_method.findText(method)
            if idx >= 0:
                self.combo_method.setCurrentIndex(idx)
            # Angle targets
            at = setup.get("angle_targets", {})
            for key, inp in self.angle_inputs.items():
                inp.setText(str(at.get(key, 0)))
        except Exception as e:
            print(f"_load_setup_data error: {e}")

    def _add_video_from_file(self):
        """Browse for an existing MP4 and add it as a video slot."""
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(self, "No Patient",
                                "No patient loaded. Please fill in the Patient Profile tab first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if not path:
            return
        label = self.combo_exercise_label.currentText()
        slot = VideoSlotWidget(
            len(self.video_slots) + 1, path,
            None,  # no thumbnail for externally-added files
            label,
        )
        slot._angle_meta = {}
        slot._created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        slot._notes = ""
        slot.deleted.connect(self._remove_video_slot)
        slot.model_selected.connect(self._on_model_selected)
        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
        self.video_slots.append(slot)
        # Remove placeholder if present
        for i in range(self.video_layout.count() - 1, -1, -1):
            item = self.video_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QLabel) and w.objectName() == "NoVideosPlaceholder":
                self.video_layout.removeWidget(w)
                w.deleteLater()
        self._persist_video_metadata()

    def _on_model_selected(self, slot: "VideoSlotWidget"):
        """Mark one video as the patient model; deselect all others."""
        for s in self.video_slots:
            s.set_as_model(s is slot)
        self._save_model_video(slot)

    def _save_model_video(self, slot: "VideoSlotWidget"):
        pid = self._get_pid()
        if not pid:
            return
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        data: dict = {}
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
            except Exception:
                pass
        data["model_video"] = {
            "path": str(slot.video_path),
            "thumb": str(slot.thumb_path) if slot.thumb_path else "",
            "exercise": slot.name_lbl.text(),
        }
        json_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(
                self, "Model Set",
                f"'{slot.name_lbl.text()}' is now the patient model video.\n"
                "It will play in the right panel during exercise.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save model video: {e}")

    # ── Recording ────────────────────────────────────────────────────────────
    @pyqtSlot(float, float)
    def _on_angles(self, knee: float, hip: float):
        self._last_knee = knee
        self._last_hip = hip
        self.lbl_setup_knee.setText(f"{knee:.1f}")
        self.lbl_setup_hip.setText(f"{hip:.1f}")
        if self.recording and knee > 0:
            self._knee_samples.append(knee)
            self._hip_samples.append(hip)

    @pyqtSlot(object)
    def _on_bgr_frame(self, bgr):
        self.current_frame_bgr = bgr
        if self._video_writer and self._video_writer.isOpened():
            self._video_writer.write(bgr)
            self._record_frame_count += 1
            if self._record_frame_count % 20 == 0:
                secs = self._record_frame_count // 20
                self.lbl_rec_status.setText(f"⏺  {secs}s recorded")

    def toggle_recording(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        if self.current_frame_bgr is None:
            QMessageBox.warning(self, "No Camera", "Camera not ready. Please wait.")
            return
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(
                self, "No Patient",
                "No patient loaded. Please fill in the Patient Profile tab and save it first."
            )
            return
        vid_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "videos"
        thumb_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "thumbs"
        vid_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        exercise_label = self.combo_exercise_label.currentText()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = exercise_label.replace(" ", "_").replace("/", "_")
        filename = f"{safe_label}_{timestamp}.mp4"
        video_path = vid_dir / filename

        h, w = self.current_frame_bgr.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._video_writer = cv2.VideoWriter(str(video_path), fourcc, 20.0, (w, h))
        if not self._video_writer.isOpened():
            QMessageBox.warning(self, "Error", "Could not open VideoWriter. Check codec support.")
            self._video_writer = None
            return

        self._recording_path = str(video_path)
        self._thumb_path = str(thumb_dir / f"{Path(filename).stem}.jpg")
        self._record_frame_count = 0
        self._knee_samples.clear()
        self._hip_samples.clear()
        self.recording = True
        self.btn_rec.setText("⏹  STOP RECORDING")
        self.btn_rec.setStyleSheet(
            f"background-color: {ModernTheme.ACCENT_DANGER}; color: white; "
            "font-weight: bold; border-radius: 6px;"
        )
        self.lbl_rec_status.setText("⏺  Recording...")

    def _stop_recording(self):
        if self._video_writer:
            self._video_writer.release()
            self._video_writer = None
        self.recording = False
        self.btn_rec.setText("⏺  START RECORDING")
        self.btn_rec.setStyleSheet(
            f"background-color: {ModernTheme.ACCENT_SUCCESS}; color: white; "
            "font-weight: bold; border-radius: 6px;"
        )
        secs = self._record_frame_count // 20
        self.lbl_rec_status.setText(f"Saved ({secs}s)")

        # Save thumbnail from last captured frame
        if self.current_frame_bgr is not None and self._thumb_path:
            try:
                thumb = cv2.resize(self.current_frame_bgr, (160, 100))
                cv2.imwrite(self._thumb_path, thumb)
            except Exception as e:
                print(f"Thumbnail error: {e}")
                self._thumb_path = None

        if self._recording_path and Path(self._recording_path).exists():
            label = self.combo_exercise_label.currentText()
            # Compute angle stats for the recording
            angle_meta = {}
            if self._knee_samples:
                angle_meta = {
                    "knee_min": round(min(self._knee_samples), 1),
                    "knee_max": round(max(self._knee_samples), 1),
                    "hip_min":  round(min(self._hip_samples), 1) if self._hip_samples else 0,
                    "hip_max":  round(max(self._hip_samples), 1) if self._hip_samples else 0,
                }
            self._add_video_slot(self._recording_path, self._thumb_path, label,
                                 angle_meta=angle_meta)
            self._persist_video_metadata()

        self._knee_samples.clear()
        self._hip_samples.clear()
        self._recording_path = None
        self._thumb_path = None

    def _add_video_slot(self, video_path: str, thumb_path: str | None, label: str,
                        angle_meta: dict | None = None):
        idx = len(self.video_slots) + 1
        slot = VideoSlotWidget(idx, video_path, thumb_path, label)
        slot._angle_meta = angle_meta or {}
        if angle_meta:
            tip = (f"Knee: {angle_meta.get('knee_min', 0):.0f}°–"
                   f"{angle_meta.get('knee_max', 0):.0f}°  "
                   f"Hip: {angle_meta.get('hip_min', 0):.0f}°–"
                   f"{angle_meta.get('hip_max', 0):.0f}°")
            slot.setToolTip(tip)
        slot.deleted.connect(self._remove_video_slot)
        slot.model_selected.connect(self._on_model_selected)
        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
        self.video_slots.append(slot)

    def stop_recording_if_needed(self):
        if self.recording:
            self._stop_recording()

    # ── Camera ───────────────────────────────────────────────────────────────
    def start_camera(self):
        if self.thread is None:
            self.thread = SimpleCameraThread()
            self.thread.change_pixmap_signal.connect(self.update_image)
            self.thread.bgr_frame_signal.connect(self._on_bgr_frame)
            self.thread.angles_signal.connect(self._on_angles)
            self.thread.start()
        self.refresh_patient()

    def stop_camera(self):
        self.stop_recording_if_needed()
        self._persist_video_metadata()   # auto-save when leaving Setup tab
        if self.thread:
            try:
                self.thread.change_pixmap_signal.disconnect()
                self.thread.bgr_frame_signal.disconnect()
                self.thread.angles_signal.disconnect()
            except Exception:
                pass
            self.thread.stop()
            self.thread = None
        self.lbl_setup_knee.setText("—")
        self.lbl_setup_hip.setText("—")

    @pyqtSlot(QImage)
    def update_image(self, qt_img: QImage):
        self.cam_frame.set_image(qt_img)


# ─────────────────────────── GENERIC FORM ────────────────────────────────────
class GenericFormWidget(QWidget):
    def __init__(self, title, fields, save_key):
        super().__init__()
        self.save_key = save_key
        self.inputs = {}

        layout = QVBoxLayout(self)
        layout.addWidget(SubHeaderLabel(title))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        form_layout = QFormLayout(content)
        form_layout.setSpacing(15)

        for label, widget_type in fields:
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #bdc3c7; font-weight: bold;")
            if widget_type == "text":
                inp = QLineEdit()
            elif widget_type == "area":
                inp = QTextEdit()
                inp.setMaximumHeight(100)
            elif isinstance(widget_type, list):
                inp = QComboBox()
                inp.addItems(widget_type)
            else:
                inp = QLineEdit()
            form_layout.addRow(lbl, inp)
            self.inputs[label] = inp

        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn_save = QPushButton("Save Changes")
        btn_save.setObjectName("Primary")
        btn_save.clicked.connect(self.save_data)
        layout.addWidget(btn_save, alignment=Qt.AlignmentFlag.AlignRight)

    def save_data(self):
        data = {}
        for k, v in self.inputs.items():
            if isinstance(v, QLineEdit):
                data[k] = v.text()
            elif isinstance(v, QTextEdit):
                data[k] = v.toPlainText()
            elif isinstance(v, QComboBox):
                data[k] = v.currentText()
        PATIENT_DATA_STORE[self.save_key] = data
        QMessageBox.information(self, "Success", "Data saved successfully!")


# ─────────────────────────── EXERCISE FORM ───────────────────────────────────
class ExerciseForm(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(SubHeaderLabel("Exercise Schedule"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        form = QVBoxLayout(content)

        grp_type = QGroupBox("Exercise Type")
        gl = QVBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Squats",
            "Seated Knee Bending",
            "Straight Leg Raises",
            "Rehabilitation - Stage 1",
            "Rehabilitation - Stage 2",
            "Strength Training",
            "Mobility Work",
            "Flexibility",
        ])
        gl.addWidget(self.type_combo)
        grp_type.setLayout(gl)
        form.addWidget(grp_type)

        grp_det = QGroupBox("Session Details")
        fl = QFormLayout()
        self.sess = QLineEdit()
        self.reps = QLineEdit()
        fl.addRow("Number of Sessions:", self.sess)
        fl.addRow("Repetitions / Duration:", self.reps)
        self.btn_add = QPushButton("Add to Schedule")
        self.btn_add.setObjectName("Success")
        self.btn_add.clicked.connect(self.add_to_table)
        fl.addRow(self.btn_add)
        grp_det.setLayout(fl)
        form.addWidget(grp_det)

        form.addWidget(QLabel("Current Schedule:"))
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Exercise Type", "Sessions", "Reps/Duration"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(150)
        form.addWidget(self.table)

        form.addWidget(QLabel("Specific Notes / Patient Issues:"))
        self.notes = QTextEdit()
        form.addWidget(self.notes)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn = QPushButton("Save Schedule")
        btn.setObjectName("Primary")
        btn.clicked.connect(self.save)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    def add_to_table(self):
        if not self.sess.text() or not self.reps.text():
            QMessageBox.warning(self, "Input Error", "Please fill in sessions and repetitions.")
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(self.type_combo.currentText()))
        self.table.setItem(row, 1, QTableWidgetItem(self.sess.text()))
        self.table.setItem(row, 2, QTableWidgetItem(self.reps.text()))
        self.sess.clear()
        self.reps.clear()

    def save(self):
        rows = []
        for row in range(self.table.rowCount()):
            rows.append({
                "exercise": self.table.item(row, 0).text() if self.table.item(row, 0) else "",
                "sessions": self.table.item(row, 1).text() if self.table.item(row, 1) else "",
                "reps": self.table.item(row, 2).text() if self.table.item(row, 2) else "",
            })
        PATIENT_DATA_STORE["exercise_schedule"] = {
            "entries": rows,
            "notes": self.notes.toPlainText(),
        }
        QMessageBox.information(self, "Saved", "Schedule updated.")


# ─────────────────────────── PATIENT SEARCH DIALOG ───────────────────────────
class PatientSearchDialog(QDialog):
    """Search and load a previously saved patient record."""

    patient_loaded = pyqtSignal(dict)   # emits full patient data dict on load

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Patient")
        self.setWindowIcon(create_app_icon())
        self.setMinimumSize(700, 480)

        self._all_patients: list[dict] = []
        self._shown_patients: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        layout.addWidget(HeaderLabel("FIND PATIENT"))

        # Search row
        search_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search by name, ID, surgeon…")
        self._search_box.textChanged.connect(self._filter)
        search_row.addWidget(self._search_box)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFixedWidth(90)
        btn_refresh.clicked.connect(self._load_patients)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        # Patient table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "ID", "Age", "Surgeon", "Source"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { alternate-background-color: #333; }"
        )
        self._table.itemDoubleClicked.connect(self._load_selected)
        self._table.currentCellChanged.connect(lambda row, *_: self._on_row_changed(row))
        layout.addWidget(self._table)

        # Detail strip
        self._detail_lbl = QLabel("")
        self._detail_lbl.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        )
        self._detail_lbl.setWordWrap(True)
        layout.addWidget(self._detail_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_load = QPushButton("Load Selected Patient")
        self._btn_load.setObjectName("Primary")
        self._btn_load.setFixedSize(200, 40)
        self._btn_load.setEnabled(False)
        self._btn_load.clicked.connect(self._load_selected)
        btn_row.addWidget(self._btn_load)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedSize(100, 40)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self._load_patients()

    # ── Data loading ────────────────────────────────────────────────────────
    def _load_patients(self):
        self._all_patients = self._scan_all_patients()
        self._filter(self._search_box.text())

    def _scan_all_patients(self) -> list[dict]:
        patients: list[dict] = []
        seen_names: set[str] = set()

        # 1. New format: patients_assets/<pid>/patient.json
        assets_dir = Path(PATIENT_ASSETS_FOLDER)
        if assets_dir.exists():
            for subdir in sorted(assets_dir.iterdir()):
                if subdir.is_dir():
                    jp = subdir / "patient.json"
                    if jp.exists():
                        try:
                            with open(jp) as f:
                                data = json.load(f)
                            data["_source"] = str(jp)
                            data["_mtime"] = jp.stat().st_mtime
                            patients.append(data)
                            seen_names.add(data.get("name", "").lower())
                        except Exception:
                            pass

        # 2. Old format: {fname}_{lname}.json in current directory
        for jp in sorted(Path(".").glob("*.json")):
            if jp.name.endswith("_sessions.json"):
                continue
            if jp.name == "unknown_sessions.json":
                continue
            try:
                with open(jp) as f:
                    data = json.load(f)
                name = data.get("name", "").lower()
                if "name" in data and name not in seen_names:
                    data["_source"] = str(jp)
                    data["_mtime"] = jp.stat().st_mtime
                    patients.append(data)
            except Exception:
                pass

        # Sort by name
        patients.sort(key=lambda d: d.get("name", "").lower())
        return patients

    def _filter(self, text: str):
        q = text.strip().lower()
        filtered = [
            p for p in self._all_patients
            if (q in p.get("name", "").lower()
                or q in p.get("id", "").lower()
                or q in p.get("surgeon", "").lower()
                or q in p.get("physio", "").lower()
                or q == "")
        ]
        self._populate_table(filtered)

    def _populate_table(self, patients: list[dict]):
        self._shown_patients = patients          # store as instance variable
        self._table.setRowCount(len(patients))
        for row, p in enumerate(patients):
            for col, val in enumerate([
                p.get("name", ""),
                p.get("id", ""),
                p.get("age", ""),
                p.get("surgeon", ""),
                Path(p.get("_source", "")).name,
            ]):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)
        self._btn_load.setEnabled(False)
        self._detail_lbl.setText(f"{len(patients)} patient(s) found.")

    def _on_row_changed(self, row: int):
        patients = getattr(self, "_shown_patients", [])
        if 0 <= row < len(patients):
            p = patients[row]
            parts = []
            if p.get("mobile"):
                parts.append(f"Mobile: {p['mobile']}")
            if p.get("surgery_date"):
                parts.append(f"Surgery: {p['surgery_date']}")
            if p.get("physio"):
                parts.append(f"Physio: {p['physio']}")
            if p.get("height") or p.get("weight"):
                parts.append(f"H/W: {p.get('height','?')}cm / {p.get('weight','?')}kg")
            self._detail_lbl.setText("  |  ".join(parts) if parts else "")
            self._btn_load.setEnabled(True)
        else:
            self._btn_load.setEnabled(False)
            self._detail_lbl.setText("")

    def _load_selected(self):
        row = self._table.currentRow()
        patients = getattr(self, "_shown_patients", [])
        if 0 <= row < len(patients):
            self.patient_loaded.emit(patients[row])
            self.accept()


# ─────────────────────────── PATIENT HISTORY PAGE ────────────────────────────
class PatientHistoryPage(QWidget):
    """Session history + recorded videos for a loaded patient."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(8)

        # Patient name header
        self._lbl_name = QLabel("— no patient loaded —")
        self._lbl_name.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 15px; "
            "font-weight: bold; border: none;"
        )
        root.addWidget(self._lbl_name)

        # Summary stat cards
        stats_row = QHBoxLayout()
        self._stat_labels: dict[str, QLabel] = {}
        for key in ["Sessions", "This Month", "Correct Reps", "Total Time", "Best Angle (°)"]:
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedHeight(72)
            cl = QVBoxLayout(card)
            t = QLabel(key)
            t.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel("—")
            v.setStyleSheet(
                f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 20px; "
                "font-weight: bold; border: none;"
            )
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._stat_labels[key] = v
            cl.addWidget(t)
            cl.addWidget(v)
            stats_row.addWidget(card)
        root.addLayout(stats_row)

        # Recorded videos
        root.addWidget(SubHeaderLabel("Recorded Videos"))
        self._video_scroll = QScrollArea()
        self._video_scroll.setWidgetResizable(True)
        self._video_scroll.setFixedHeight(165)
        self._video_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._video_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._video_container = QWidget()
        self._video_layout = QHBoxLayout(self._video_container)
        self._video_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._video_layout.setSpacing(8)
        self._video_scroll.setWidget(self._video_container)
        root.addWidget(self._video_scroll)

        # Session table
        root.addWidget(SubHeaderLabel("Session History"))
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Date & Time", "Exercise", "Duration",
            "Correct Reps", "Total Reps",
            "Left Leg\n(correct/total)", "Right Leg\n(correct/total)",
            "Min Angle (°)", "Max Angle (°)",
        ])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("QTableWidget { alternate-background-color: #333; }")
        root.addWidget(self._table)

    # ── Load data ────────────────────────────────────────────────────────────
    def load_patient(self, data: dict):
        name = data.get("name", "Unknown")
        pid  = data.get("id", "")
        surgeon = data.get("surgeon", "")
        header = name
        if pid:
            header += f"   (ID: {pid})"
        if surgeon:
            header += f"   —   Surgeon: {surgeon}"
        self._lbl_name.setText(header)

        # Load sessions directly for this patient (not via global PATIENT_DATA_STORE)
        sessions = storage.load_sessions(data)
        now = datetime.now()

        total   = len(sessions)
        month   = sum(1 for s in sessions
                      if s.get("date","").startswith(f"{now.year}-{now.month:02d}"))
        correct = sum(s.get("correct_reps", 0) for s in sessions)
        secs    = sum(s.get("duration_seconds", 0) for s in sessions)
        tstr    = f"{int(secs//3600):02d}h {int((secs%3600)//60):02d}m"
        best    = max((s.get("max_knee_angle", 0) for s in sessions), default=0)

        for key, val in [
            ("Sessions",       str(total)),
            ("This Month",     str(month)),
            ("Correct Reps",   str(correct)),
            ("Total Time",     tstr),
            ("Best Angle (°)", f"{best:.1f}"),
        ]:
            if key in self._stat_labels:
                self._stat_labels[key].setText(val)

        # Session table
        self._table.setRowCount(len(sessions))
        for row, s in enumerate(reversed(sessions)):
            dur = s.get("duration_seconds", 0)
            dur_str = f"{int(dur//60)}m {int(dur%60)}s"
            is_slr = s.get("exercise", "") == "Straight Leg Raises"
            left_s  = f"{s.get('left_correct_reps',0)}/{s.get('left_total_reps',0)}" if is_slr else "—"
            right_s = f"{s.get('right_correct_reps',0)}/{s.get('right_total_reps',0)}" if is_slr else "—"
            for col, val in enumerate([
                s.get("date","") + "  " + s.get("time",""),
                s.get("exercise",""),
                dur_str,
                str(s.get("correct_reps", 0)),
                str(s.get("total_reps", 0)),
                left_s, right_s,
                f"{s.get('min_knee_angle', 0):.1f}",
                f"{s.get('max_knee_angle', 0):.1f}",
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

        self._load_videos(data)

    def _load_videos(self, data: dict):
        # Clear old tiles
        while self._video_layout.count():
            w = self._video_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        # Merge videos from passed data and from patient.json on disk
        pid = data.get("id", "").strip()
        name = data.get("name", "").replace(" ", "_")
        folder_id = pid if pid else name
        pat_json = Path(PATIENT_ASSETS_FOLDER) / folder_id / "patient.json"

        videos = list(data.get("videos", []))
        model_path = data.get("model_video", {}).get("path", "")
        if pat_json.exists():
            try:
                with open(pat_json) as f:
                    pj = json.load(f)
                if not videos:
                    videos = pj.get("videos", [])
                if not model_path:
                    model_path = pj.get("model_video", {}).get("path", "")
            except Exception:
                pass

        if not videos:
            lbl = QLabel("No recorded videos.")
            lbl.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; border: none;")
            self._video_layout.addWidget(lbl)
            return

        for v in videos:
            thumb_path = v.get("thumb", "")
            vid_path   = v.get("path", "")
            exercise   = v.get("exercise", "")
            is_model   = bool(vid_path and vid_path == model_path)

            tile = QFrame()
            tile.setFixedSize(155, 150)
            tile.setObjectName("Card")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(4, 4, 4, 4)
            tl.setSpacing(3)

            thumb_lbl = QLabel()
            thumb_lbl.setFixedSize(145, 82)
            thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_lbl.setStyleSheet("background-color: #000; border-radius: 4px;")
            if thumb_path and Path(thumb_path).exists():
                pix = QPixmap(thumb_path).scaled(
                    145, 82,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                thumb_lbl.setPixmap(pix)
            else:
                thumb_lbl.setText("No preview")
                thumb_lbl.setStyleSheet(
                    "background:#111; color:#666; border-radius:4px; font-size:10px;"
                )
            tl.addWidget(thumb_lbl)

            ex_label = ("★ " if is_model else "") + (exercise or Path(vid_path).stem if vid_path else "—")
            lbl = QLabel(ex_label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {'#f1c40f' if is_model else ModernTheme.TEXT_GRAY}; "
                "font-size: 10px; border: none;"
            )
            lbl.setWordWrap(True)
            tl.addWidget(lbl)

            btn_play = QPushButton("▶ Play")
            btn_play.setFixedHeight(22)
            p = vid_path
            btn_play.clicked.connect(
                lambda _, vp=p: os.startfile(vp) if Path(vp).exists() else
                QMessageBox.warning(self, "Not Found", f"Video file not found:\n{vp}")
            )
            tl.addWidget(btn_play)
            self._video_layout.addWidget(tile)


# ─────────────────────────── DOCUMENTS PAGE ──────────────────────────────────
class DocumentsPage(QWidget):
    """Upload and view patient documents (PDFs, consent forms, scans)."""

    def __init__(self):
        super().__init__()
        self._patient_data: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(8)

        root.addWidget(SubHeaderLabel("Patient Documents"))

        # Toolbar
        toolbar = QHBoxLayout()
        btn_upload = QPushButton("Upload Document")
        btn_upload.setObjectName("Primary")
        btn_upload.setFixedHeight(34)
        btn_upload.clicked.connect(self._upload)
        toolbar.addWidget(btn_upload)
        toolbar.addStretch()
        root.addLayout(toolbar)

        # Table of documents
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Title", "Filename", "Date Added", "Description", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("QTableWidget { alternate-background-color: #333; }")
        root.addWidget(self._table)

        note = QLabel("Double-click a row to open the document.")
        note.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;")
        root.addWidget(note)
        self._table.itemDoubleClicked.connect(self._open_selected)

    def refresh_patient(self, patient_data: dict):
        self._patient_data = patient_data
        self._reload()

    def _reload(self):
        pj = storage.load_patient_json(self._patient_data)
        docs = pj.get("documents", [])
        self._docs = docs
        self._table.setRowCount(len(docs))
        for row, d in enumerate(docs):
            for col, val in enumerate([
                d.get("title", ""),
                d.get("filename", ""),
                d.get("date_added", ""),
                d.get("description", ""),
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._table.setItem(row, col, item)
            # Delete button
            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_DANGER}; color: white; "
                "font-size: 10px; border-radius: 3px; padding: 2px 6px;"
            )
            fname = d.get("filename", "")
            btn_del.clicked.connect(lambda _, f=fname: self._delete(f))
            self._table.setCellWidget(row, 4, btn_del)

    def _upload(self):
        if not self._patient_data:
            QMessageBox.warning(self, "No Patient", "Load a patient first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Document",
            "",
            "Documents (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.docx *.txt);;All Files (*)",
        )
        if not paths:
            return
        for src_path in paths:
            fname = Path(src_path).name
            title, ok = QInputDialog.getText(
                self, "Document Title",
                f"Title for '{fname}':",
                text=fname,
            )
            if not ok:
                title = fname
            desc, _ = QInputDialog.getText(
                self, "Description (optional)",
                "Short description:",
            )
            ok2 = storage.add_document(self._patient_data, src_path, title, desc)
            if not ok2:
                QMessageBox.warning(self, "Error", f"Could not upload: {fname}")
        self._reload()
        QMessageBox.information(self, "Uploaded", f"{len(paths)} document(s) uploaded.")

    def _delete(self, filename: str):
        reply = QMessageBox.question(
            self, "Delete Document",
            f"Delete '{filename}' permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            storage.remove_document(self._patient_data, filename)
            self._reload()

    def _open_selected(self, item):
        row = item.row()
        if 0 <= row < len(self._docs):
            fpath = self._docs[row].get("path", "")
            if fpath and Path(fpath).exists():
                try:
                    os.startfile(str(Path(fpath).resolve()))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Cannot open file:\n{e}")
            else:
                QMessageBox.warning(self, "Not Found",
                                    f"File not found:\n{fpath}")


# ─────────────────────────── REPORTS PAGE ────────────────────────────────────
class ReportsPage(QWidget):
    """Generate monthly report or full patient record PDFs."""

    def __init__(self):
        super().__init__()
        self._patient_data: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(16)
        root.addWidget(SubHeaderLabel("Reports"))

        # Monthly report card
        monthly_grp = QGroupBox("Monthly Report")
        ml = QVBoxLayout(monthly_grp)
        ml.setSpacing(8)

        ml.addWidget(QLabel("Generate a PDF summary for a specific month:"))
        m_controls = QHBoxLayout()
        m_controls.addWidget(QLabel("Month:"))
        self._month_spin = QSpinBox()
        self._month_spin.setRange(1, 12)
        self._month_spin.setValue(datetime.now().month)
        self._month_spin.setFixedWidth(60)
        m_controls.addWidget(self._month_spin)
        m_controls.addWidget(QLabel("Year:"))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2020, 2040)
        self._year_spin.setValue(datetime.now().year)
        self._year_spin.setFixedWidth(80)
        m_controls.addWidget(self._year_spin)
        m_controls.addStretch()
        ml.addLayout(m_controls)

        btn_monthly = QPushButton("Generate Monthly Report PDF")
        btn_monthly.setObjectName("Primary")
        btn_monthly.setFixedHeight(36)
        btn_monthly.clicked.connect(self._gen_monthly)
        ml.addWidget(btn_monthly, alignment=Qt.AlignmentFlag.AlignLeft)

        self._lbl_monthly_status = QLabel("")
        self._lbl_monthly_status.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 11px; border: none;"
        )
        ml.addWidget(self._lbl_monthly_status)
        root.addWidget(monthly_grp)

        # Full record card
        full_grp = QGroupBox("Full Patient Record")
        fl = QVBoxLayout(full_grp)
        fl.setSpacing(8)
        fl.addWidget(QLabel(
            "Export a complete patient record including profile, thresholds,\n"
            "videos, documents index, and full session history:"
        ))
        btn_full = QPushButton("Export Full Record PDF")
        btn_full.setObjectName("Success")
        btn_full.setFixedHeight(36)
        btn_full.clicked.connect(self._gen_full)
        fl.addWidget(btn_full, alignment=Qt.AlignmentFlag.AlignLeft)

        self._lbl_full_status = QLabel("")
        self._lbl_full_status.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 11px; border: none;"
        )
        fl.addWidget(self._lbl_full_status)
        root.addWidget(full_grp)

        root.addStretch()

    def refresh_patient(self, patient_data: dict):
        self._patient_data = patient_data
        self._lbl_monthly_status.setText("")
        self._lbl_full_status.setText("")

    def _gen_monthly(self):
        if not self._patient_data:
            QMessageBox.warning(self, "No Patient", "Load a patient first.")
            return
        sessions = storage.load_sessions(self._patient_data)
        year  = self._year_spin.value()
        month = self._month_spin.value()
        self._lbl_monthly_status.setText("Generating…")
        QApplication.processEvents()
        out = reports.generate_monthly_report(self._patient_data, sessions, year, month)
        if out:
            self._lbl_monthly_status.setText(f"Saved: {out.name}")
            try:
                os.startfile(str(out.resolve()))
            except Exception:
                pass
        else:
            self._lbl_monthly_status.setText("Generation failed. Check console.")
            QMessageBox.warning(self, "Error", "Could not generate report.\nCheck console for details.")

    def _gen_full(self):
        if not self._patient_data:
            QMessageBox.warning(self, "No Patient", "Load a patient first.")
            return
        # Merge stored patient.json (has videos, thresholds, docs) with live data
        pj = storage.load_patient_json(self._patient_data)
        merged = {**self._patient_data, **pj}
        sessions = storage.load_sessions(self._patient_data)
        self._lbl_full_status.setText("Generating…")
        QApplication.processEvents()
        out = reports.generate_full_record(merged, sessions)
        if out:
            self._lbl_full_status.setText(f"Saved: {out.name}")
            try:
                os.startfile(str(out.resolve()))
            except Exception:
                pass
        else:
            self._lbl_full_status.setText("Generation failed. Check console.")
            QMessageBox.warning(self, "Error", "Could not generate report.\nCheck console for details.")


# ─────────────────────────── PATIENT FILE PAGE ───────────────────────────────
class PatientFilePage(QWidget):
    """Hospital-style read-only patient summary — shows all key info + PDF export."""

    def __init__(self):
        super().__init__()
        self._patient_data: dict = {}
        self._sessions: list = []
        # Set by PatientDashboard to allow navigation to other pages
        self._navigate_to = None   # callable(page_index: int)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(6)

        # ── Top toolbar ──────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        title_lbl = QLabel("PATIENT FILE")
        title_lbl.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 18px; "
            "font-weight: bold; border: none;"
        )
        toolbar.addWidget(title_lbl)
        toolbar.addStretch()

        # Quick-action shortcuts — visible once a patient is loaded
        _btn_style = (
            "font-size: 11px; padding: 4px 10px; border-radius: 4px; "
            f"background-color: {ModernTheme.BG_LIGHT}; "
            "border: 1px solid #555; color: #ccc;"
        )
        btn_edit_info = QPushButton("✎  Edit Profile")
        btn_edit_info.setFixedHeight(28)
        btn_edit_info.setStyleSheet(_btn_style)
        btn_edit_info.setToolTip("Go to Patient Profile and edit information")
        btn_edit_info.clicked.connect(lambda: self._nav(0))   # PAGE_INFO = 0
        toolbar.addWidget(btn_edit_info)

        btn_setup = QPushButton("⚙  Setup & Targets")
        btn_setup.setFixedHeight(28)
        btn_setup.setStyleSheet(_btn_style)
        btn_setup.setToolTip("Edit exercise setup, angle targets and recorded videos")
        btn_setup.clicked.connect(lambda: self._nav(1))       # PAGE_SETUP = 1
        toolbar.addWidget(btn_setup)

        btn_progress = QPushButton("📈  View Progress")
        btn_progress.setFixedHeight(28)
        btn_progress.setStyleSheet(_btn_style)
        btn_progress.setToolTip("View session history and patient improvement")
        btn_progress.clicked.connect(lambda: self._nav(4))    # PAGE_HISTORY = 4
        toolbar.addWidget(btn_progress)

        root.addLayout(toolbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {ModernTheme.ACCENT_PRIMARY};")
        sep.setFixedHeight(2)
        root.addWidget(sep)

        # ── Scrollable content ────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        cl = QVBoxLayout(content)
        cl.setSpacing(12)

        # Identity grid
        id_grp = QGroupBox("Patient Identity")
        id_grp.setStyleSheet(
            f"QGroupBox {{ border: 1px solid #444; border-radius: 6px; "
            f"margin-top: 0.8em; }} QGroupBox::title {{ subcontrol-origin: margin; "
            f"left: 8px; color: {ModernTheme.ACCENT_PRIMARY}; }}"
        )
        id_gl = QGridLayout(id_grp)
        id_gl.setSpacing(8)
        self._id_labels: dict[str, QLabel] = {}
        id_fields = [
            ("Name",         "name"),      ("Patient ID",    "id"),
            ("Age",          "age"),       ("Gender",        "gender"),
            ("Mobile",       "mobile"),    ("Surgery Date",  "surgery_date"),
            ("Surgeon",      "surgeon"),   ("Physiotherapist","physio"),
            ("Height (cm)",  "height"),    ("Weight (kg)",   "weight"),
        ]
        for i, (caption, key) in enumerate(id_fields):
            r, c = divmod(i, 2)
            lbl_c = QLabel(f"{caption}:")
            lbl_c.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; border: none;")
            lbl_v = QLabel("—")
            lbl_v.setStyleSheet("color: white; border: none; font-weight: bold;")
            id_gl.addWidget(lbl_c, r, c * 2)
            id_gl.addWidget(lbl_v, r, c * 2 + 1)
            self._id_labels[key] = lbl_v
        cl.addWidget(id_grp)

        # Session summary stats
        stats_grp = QGroupBox("Session Summary")
        stats_grp.setStyleSheet(id_grp.styleSheet())
        stats_gl = QHBoxLayout(stats_grp)
        self._stat_vals: dict[str, QLabel] = {}
        for key in ["Sessions", "This Month", "Correct Reps", "Total Time", "Best Angle (°)"]:
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedHeight(68)
            card_l = QVBoxLayout(card)
            t = QLabel(key)
            t.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 10px; border: none;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel("—")
            v.setStyleSheet(
                f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 18px; "
                "font-weight: bold; border: none;"
            )
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_l.addWidget(t)
            card_l.addWidget(v)
            self._stat_vals[key] = v
            stats_gl.addWidget(card)
        cl.addWidget(stats_grp)

        # Clinical notes
        notes_grp = QGroupBox("Clinical Notes")
        notes_grp.setStyleSheet(id_grp.styleSheet())
        notes_gl = QVBoxLayout(notes_grp)
        self._notes_labels: dict[str, QLabel] = {}
        for caption, key in [
            ("Surgery / Procedure", "surgery_date"),
            ("Functional Goals",    "goals"),
            ("Medical History",     "history"),
            ("Current Medication",  "meds"),
            ("Nutrition Notes",     "nutrition"),
        ]:
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(8)
            cap = QLabel(f"{caption}:")
            cap.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;")
            cap.setFixedWidth(180)
            cap.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            val = QLabel("—")
            val.setStyleSheet(
                "color: white; font-size: 11px; border: none; "
                "background: #222; border-radius: 4px; padding: 4px 6px;"
            )
            val.setWordWrap(True)
            row_l.addWidget(cap)
            row_l.addWidget(val, stretch=1)
            notes_gl.addWidget(row_w)
            self._notes_labels[key] = val
        cl.addWidget(notes_grp)

        # Documents list
        docs_grp = QGroupBox("Documents on File")
        docs_grp.setStyleSheet(id_grp.styleSheet())
        docs_gl = QVBoxLayout(docs_grp)
        self._docs_list = QLabel("No documents on file.")
        self._docs_list.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        )
        self._docs_list.setWordWrap(True)
        docs_gl.addWidget(self._docs_list)
        cl.addWidget(docs_grp)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ── Navigation helper ─────────────────────────────────────────────────────
    def _nav(self, page_index: int):
        """Navigate the parent PatientDashboard to a different page."""
        if callable(self._navigate_to):
            self._navigate_to(page_index)

    # ── Data refresh ─────────────────────────────────────────────────────────
    def refresh_patient(self, patient_data: dict):
        self._patient_data = patient_data
        # Merge with any extra data in patient.json (thresholds, docs, etc.)
        pj = storage.load_patient_json(patient_data)
        merged = {**patient_data, **pj}
        sessions = storage.load_sessions(patient_data)
        self._sessions = sessions
        self._populate(merged, sessions)

    def _populate(self, data: dict, sessions: list):
        # Identity
        for key, lbl in self._id_labels.items():
            lbl.setText(str(data.get(key, "") or "—"))

        # Notes
        for key, lbl in self._notes_labels.items():
            lbl.setText(str(data.get(key, "") or "—"))

        # Stats
        now = datetime.now()
        total  = len(sessions)
        month  = sum(1 for s in sessions
                     if s.get("date","").startswith(f"{now.year}-{now.month:02d}"))
        correct= sum(s.get("correct_reps", 0) for s in sessions)
        secs   = sum(s.get("duration_seconds", 0) for s in sessions)
        best   = max((s.get("max_knee_angle", 0) for s in sessions), default=0)
        tstr   = f"{int(secs//3600):02d}h {int((secs%3600)//60):02d}m"
        for key, val in [("Sessions", str(total)), ("This Month", str(month)),
                         ("Correct Reps", str(correct)), ("Total Time", tstr),
                         ("Best Angle (°)", f"{best:.1f}")]:
            self._stat_vals[key].setText(val)

        # Documents
        docs = data.get("documents", [])
        if docs:
            lines = [f"• {d.get('title','—')}  ({d.get('filename','—')})  — {d.get('date_added','')}"
                     for d in docs]
            self._docs_list.setText("\n".join(lines))
        else:
            self._docs_list.setText("No documents on file.")

    # ── Export ───────────────────────────────────────────────────────────────
    def _export_pdf(self):
        if not self._patient_data:
            QMessageBox.warning(self, "No Patient", "Load a patient first.")
            return
        pj = storage.load_patient_json(self._patient_data)
        merged = {**self._patient_data, **pj}
        sessions = storage.load_sessions(self._patient_data)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        out = reports.generate_full_record(merged, sessions)
        QApplication.restoreOverrideCursor()
        if out:
            QMessageBox.information(self, "Exported", f"Saved to:\n{out}")
            try:
                os.startfile(str(out.resolve()))
            except Exception:
                pass
        else:
            QMessageBox.warning(self, "Error", "Could not generate PDF. Check console.")


# ─────────────────────────── PATIENT DASHBOARD ───────────────────────────────
class PatientDashboard(QDialog):
    # page index constants
    PAGE_INFO      = 0
    PAGE_SETUP     = 1
    PAGE_EXERCISE  = 2
    PAGE_DOCUMENTS = 3   # Documents (replaces old Consent stub)
    PAGE_HISTORY   = 4
    PAGE_FILE      = 5   # Patient File (hospital summary)
    PAGE_REPORTS   = 6

    def __init__(self, parent=None, standalone: bool = False):
        super().__init__(parent)
        self._standalone = standalone
        self.setWindowTitle("Patient Management Dashboard")
        self.setWindowIcon(create_app_icon())
        self.resize(1100, 740)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-right: 1px solid #444;"
        )
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(HeaderLabel("ADMIN"))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #444;")
        sidebar_layout.addWidget(sep)

        self.list_widget = QListWidget()
        self.list_widget.addItems([
            "Patient Profile",
            "Setup & Videos",
            "Exercise Schedule",
            "Documents",
            "Session History",
            "Patient File",
            "Reports",
        ])
        self.list_widget.setCurrentRow(0)
        self.list_widget.currentRowChanged.connect(self.display_page)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setFixedHeight(310)
        sidebar_layout.addWidget(self.list_widget)
        sidebar_layout.addStretch()

        btn_back = QPushButton("Back")
        btn_back.setStyleSheet("background-color: #555;")
        btn_back.setAutoDefault(False)
        btn_back.setDefault(False)
        btn_back.clicked.connect(self.accept)
        sidebar_layout.addWidget(btn_back)
        main_layout.addWidget(sidebar)

        # ── Content area ─────────────────────────────────────────────────────
        content_area = QFrame()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.stack = QStackedWidget()

        # 0 — Patient Profile (merged info form)
        self.form = MergedPatientForm()
        self.stack.addWidget(self.form)

        # 1 — Setup & Videos
        self.setup_page = SetupPage()
        self.stack.addWidget(self.setup_page)

        # 2 — Exercise Schedule
        self.stack.addWidget(ExerciseForm())

        # 3 — Documents (replaces old stub consent form)
        self.documents_page = DocumentsPage()
        self.stack.addWidget(self.documents_page)

        # 4 — Session History / Progress
        self.history_page = PatientHistoryPage()
        self.stack.addWidget(self.history_page)

        # 5 — Patient File (hospital-style printable summary)
        self.patient_file_page = PatientFilePage()
        # Wire quick-action navigation so PatientFilePage can jump to other tabs
        self.patient_file_page._navigate_to = self.list_widget.setCurrentRow
        self.stack.addWidget(self.patient_file_page)

        # 6 — Reports (PDF generation)
        self.reports_page = ReportsPage()
        self.stack.addWidget(self.reports_page)

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_area)

    # ── Navigation ───────────────────────────────────────────────────────────
    def display_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == self.PAGE_SETUP:
            self.setup_page.start_camera()
            # Always re-read patient data when entering Setup so new/saved patients both work
            self.setup_page.refresh_patient()
        else:
            self.setup_page.stop_camera()
        # Refresh data-dependent pages on every visit
        data = PATIENT_DATA_STORE.get("merged_info", {})
        if index == self.PAGE_DOCUMENTS:
            self.documents_page.refresh_patient(data)
        elif index == self.PAGE_FILE:
            self.patient_file_page.refresh_patient(data)
        elif index == self.PAGE_REPORTS:
            self.reports_page.refresh_patient(data)

    # ── Find Patient ─────────────────────────────────────────────────────────
    def _load_patient(self, data: dict):
        """Load patient into all dashboard pages."""
        PATIENT_DATA_STORE["merged_info"] = data
        name = data.get("name", "").strip()
        pid  = data.get("id", "").strip()
        label = name if name else pid if pid else "Unknown"
        self.setWindowTitle(f"Patient Dashboard — {label}")

        # Fill patient profile form
        self.form.load_patient(data)

        # Refresh history page
        self.history_page.load_patient(data)

        # Refresh data-bound pages
        self.documents_page.refresh_patient(data)
        self.patient_file_page.refresh_patient(data)
        self.reports_page.refresh_patient(data)

        # Refresh setup page (loads saved videos, method, angle_targets)
        self.setup_page.refresh_patient()

        # Navigate to Patient File tab for instant hospital-style summary
        self.list_widget.setCurrentRow(self.PAGE_FILE)

    # ── Window close ─────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self.setup_page.stop_camera()
        super().closeEvent(event)


# ─────────────────────────── PROGRESS DIALOG ─────────────────────────────────
class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Progress Report")
        self.setWindowIcon(create_app_icon())
        self.resize(900, 600)

        sessions = storage.load_sessions(PATIENT_DATA_STORE.get("merged_info", {}))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(HeaderLabel("PROGRESS REPORT"))

        # ── Summary cards ──
        cards_row = QHBoxLayout()
        now = datetime.now()

        total_sessions = len(sessions)
        month_sessions = sum(
            1 for s in sessions
            if s.get("date", "").startswith(f"{now.year}-{now.month:02d}")
        )
        total_correct = sum(s.get("correct_reps", 0) for s in sessions)
        total_secs = sum(s.get("duration_seconds", 0) for s in sessions)
        total_time_str = f"{int(total_secs // 3600):02d}h {int((total_secs % 3600) // 60):02d}m"
        best_angle = max((s.get("max_knee_angle", 0) for s in sessions), default=0)

        for title, value in [
            ("Total Sessions", str(total_sessions)),
            ("This Month", str(month_sessions)),
            ("Correct Reps", str(total_correct)),
            ("Total Time", total_time_str),
            ("Best Angle (\u00b0)", f"{best_angle:.1f}"),
        ]:
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedHeight(80)
            cl = QVBoxLayout(card)
            t = QLabel(title)
            t.setStyleSheet(
                f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
            )
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v = QLabel(value)
            v.setStyleSheet(
                f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 20px; "
                "font-weight: bold; border: none;"
            )
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cl.addWidget(t)
            cl.addWidget(v)
            cards_row.addWidget(card)
        layout.addLayout(cards_row)

        # ── History table ──
        layout.addWidget(SubHeaderLabel("Session History"))
        table = QTableWidget()
        table.setColumnCount(9)
        table.setHorizontalHeaderLabels([
            "Date & Time", "Exercise", "Duration",
            "Correct Reps", "Total Reps",
            "Left Leg\n(correct/total)", "Right Leg\n(correct/total)",
            "Min Angle (\u00b0)", "Max Angle (\u00b0)",
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setRowCount(len(sessions))
        for row, s in enumerate(reversed(sessions)):
            dur = s.get("duration_seconds", 0)
            dur_str = f"{int(dur // 60)}m {int(dur % 60)}s"
            is_slr = s.get("exercise", "") == "Straight Leg Raises"
            left_str = f"{s.get('left_correct_reps',0)}/{s.get('left_total_reps',0)}" if is_slr else "—"
            right_str = f"{s.get('right_correct_reps',0)}/{s.get('right_total_reps',0)}" if is_slr else "—"
            for col, val in enumerate([
                s.get("date", "") + "  " + s.get("time", ""),
                s.get("exercise", ""),
                dur_str,
                str(s.get("correct_reps", 0)),
                str(s.get("total_reps", 0)),
                left_str,
                right_str,
                f"{s.get('min_knee_angle', 0):.1f}",
                f"{s.get('max_knee_angle', 0):.1f}",
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)
        layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("Primary")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


# ─────────────────────────── MAIN WINDOW ─────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KneeConnect - Professional Edition")
        self.setWindowIcon(create_app_icon())
        self.resize(1200, 750)

        # ── State ──
        self.thread_cam: VisionCameraThread | None = None
        self.is_running = False
        self.camera_on = True

        # ── TTS worker ──
        self.tts_worker = TTSWorker(cooldown_seconds=4.0)
        self.tts_worker.start()

        # ── Session tracking ──
        self.session_start_time: float | None = None
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0
        self.session_exercise = ""
        # Per-side rep tracking (Straight Leg Raises)
        self.session_left_correct = 0
        self.session_left_total = 0
        self.session_right_correct = 0
        self.session_right_total = 0

        # ── Root layout ──
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(20, 15, 20, 15)

        # ── Top bar ──
        top_bar = QHBoxLayout()
        logo = QLabel("KNEE CONNECT")
        logo.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {ModernTheme.ACCENT_PRIMARY}; border: none;"
        )
        top_bar.addWidget(logo)
        top_bar.addSpacing(20)

        # Patient status label — read-only, shows current patient
        _info = PATIENT_DATA_STORE.get("merged_info", {})
        _name = _info.get("name", "").strip()
        _pid  = _info.get("id", "").strip()
        _label = _name if _name else (_pid if _pid else "")
        _welcome = f"Welcome, {_label}" if _label else "Welcome"
        self.lbl_patient_badge = QLabel(f"Current Patient: {_label}" if _label else _welcome)
        self.lbl_patient_badge.setStyleSheet(
            "color: #2ecc71; font-size: 13px; font-weight: bold; border: none;"
        )
        top_bar.addWidget(self.lbl_patient_badge)

        top_bar.addStretch()

        self.lbl_status = QLabel("System Ready")
        self.lbl_status.setStyleSheet("color: #777; border: none;")
        top_bar.addWidget(self.lbl_status)
        root.addLayout(top_bar)

        # ── Main content row: camera | instructional video ──
        content_row = QHBoxLayout()

        # Camera panel
        cam_card = QFrame()
        cam_card.setObjectName("Card")
        cam_card_layout = QVBoxLayout(cam_card)
        cam_card_layout.setContentsMargins(8, 8, 8, 8)

        cam_top = QHBoxLayout()
        cam_lbl_title = QLabel("Live Camera")
        cam_lbl_title.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;"
        )
        cam_top.addWidget(cam_lbl_title)
        cam_top.addStretch()

        self.btn_cam_toggle = QPushButton("Camera Off")
        self.btn_cam_toggle.setFixedSize(100, 26)
        self.btn_cam_toggle.setStyleSheet(
            "background-color: rgba(255,255,255,0.08); border: 1px solid #555; "
            "border-radius: 4px; font-size: 12px;"
        )
        self.btn_cam_toggle.clicked.connect(self.toggle_camera_power)
        cam_top.addWidget(self.btn_cam_toggle)
        cam_card_layout.addLayout(cam_top)

        self.feed_label = QLabel("Initializing Camera…")
        self.feed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feed_label.setStyleSheet("color: #555; border: none;")
        self.feed_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cam_card_layout.addWidget(self.feed_label)

        # Live stats bar (reps + angles)
        stats_bar = QHBoxLayout()
        stats_bar.setContentsMargins(4, 2, 4, 2)

        title_style = f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        value_style = (f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 18px; "
                       "font-weight: bold; border: none;")

        # REPS
        reps_col = QVBoxLayout()
        self._lbl_reps_title = QLabel("REPS")
        self._lbl_reps_title.setStyleSheet(title_style)
        self._lbl_reps_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_reps = QLabel("—")
        self.lbl_reps.setStyleSheet(value_style)
        self.lbl_reps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reps_col.addWidget(self._lbl_reps_title)
        reps_col.addWidget(self.lbl_reps)

        # KNEE ANGLE
        knee_col = QVBoxLayout()
        self._lbl_knee_title = QLabel("KNEE ANGLE (\u00b0)")
        self._lbl_knee_title.setStyleSheet(title_style)
        self._lbl_knee_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_knee_angle = QLabel("—")
        self.lbl_knee_angle.setStyleSheet(value_style)
        self.lbl_knee_angle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        knee_col.addWidget(self._lbl_knee_title)
        knee_col.addWidget(self.lbl_knee_angle)

        # HIP ANGLE
        hip_col = QVBoxLayout()
        self._lbl_hip_title = QLabel("HIP ANGLE (\u00b0)")
        self._lbl_hip_title.setStyleSheet(title_style)
        self._lbl_hip_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hip_angle = QLabel("—")
        self.lbl_hip_angle.setStyleSheet(value_style)
        self.lbl_hip_angle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hip_col.addWidget(self._lbl_hip_title)
        hip_col.addWidget(self.lbl_hip_angle)

        # LEFT LEG REPS (only shown for Straight Leg Raises)
        left_col = QVBoxLayout()
        self._lbl_left_title = QLabel("LEFT LEG")
        self._lbl_left_title.setStyleSheet(title_style)
        self._lbl_left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_left_reps = QLabel("—")
        self.lbl_left_reps.setStyleSheet(value_style)
        self.lbl_left_reps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_col.addWidget(self._lbl_left_title)
        left_col.addWidget(self.lbl_left_reps)

        # RIGHT LEG REPS (only shown for Straight Leg Raises)
        right_col = QVBoxLayout()
        self._lbl_right_title = QLabel("RIGHT LEG")
        self._lbl_right_title.setStyleSheet(title_style)
        self._lbl_right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_right_reps = QLabel("—")
        self.lbl_right_reps.setStyleSheet(value_style)
        self.lbl_right_reps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_col.addWidget(self._lbl_right_title)
        right_col.addWidget(self.lbl_right_reps)

        # Container widgets so we can show/hide them together
        self._left_col_widget = QWidget()
        self._left_col_widget.setLayout(left_col)
        self._left_col_widget.hide()
        self._right_col_widget = QWidget()
        self._right_col_widget.setLayout(right_col)
        self._right_col_widget.hide()

        stats_bar.addStretch()
        stats_bar.addLayout(reps_col)
        stats_bar.addStretch()
        stats_bar.addWidget(self._left_col_widget)
        stats_bar.addStretch()
        stats_bar.addWidget(self._right_col_widget)
        stats_bar.addStretch()
        stats_bar.addLayout(knee_col)
        stats_bar.addStretch()
        stats_bar.addLayout(hip_col)
        stats_bar.addStretch()
        cam_card_layout.addLayout(stats_bar)

        content_row.addWidget(cam_card, stretch=3)

        # Instructional video panel
        instr_card = QFrame()
        instr_card.setObjectName("Card")
        instr_layout = QVBoxLayout(instr_card)
        instr_layout.setContentsMargins(8, 8, 8, 8)

        instr_title = QLabel("Instructional Video")
        instr_title.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;"
        )
        instr_layout.addWidget(instr_title)

        self.video_widget = QVideoWidget()
        instr_layout.addWidget(self.video_widget)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.errorOccurred.connect(self._on_media_error)

        content_row.addWidget(instr_card, stretch=2)

        root.addLayout(content_row, stretch=1)

        # ── Control bar ──
        control_bar = QFrame()
        control_bar.setObjectName("Card")
        control_bar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-radius: 40px;"
        )
        control_bar.setFixedHeight(80)

        ctrl = QHBoxLayout(control_bar)
        ctrl.setContentsMargins(30, 10, 30, 10)

        self.btn_exercise = QPushButton("Select Exercise")
        self.btn_exercise.setFixedWidth(150)
        ctrl.addWidget(self.btn_exercise)

        ctrl.addSpacing(10)

        leg_label = QLabel("Leg:")
        leg_label.setStyleSheet("color: #bdc3c7; font-size: 12px; border: none;")
        ctrl.addWidget(leg_label)
        self.combo_leg = QComboBox()
        self.combo_leg.addItems(["Auto", "Right Leg", "Left Leg"])
        self.combo_leg.setFixedWidth(110)
        self.combo_leg.currentTextChanged.connect(self._on_leg_changed)
        ctrl.addWidget(self.combo_leg)

        ctrl.addSpacing(20)

        self.btn_start = QPushButton("START")
        self.btn_start.setObjectName("Primary")
        self.btn_start.setFixedSize(110, 46)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("Danger")
        self.btn_stop.setFixedSize(110, 46)

        ctrl.addWidget(self.btn_start)
        ctrl.addWidget(self.btn_stop)
        ctrl.addStretch()

        _prog_label = "Reports" if CURRENT_USER_ROLE == "admin" else "Progress"
        self.btn_show_progress = QPushButton(_prog_label)
        self.btn_show_progress.setFixedWidth(110)
        if CURRENT_USER_ROLE == "admin":
            self.btn_show_progress.setObjectName("Primary")
        ctrl.addWidget(self.btn_show_progress)

        _admin_btn_label = "Patient Dashboard" if CURRENT_USER_ROLE == "admin" else "My Profile"
        self.btn_patient_admin = QPushButton(_admin_btn_label)
        self.btn_patient_admin.setFixedWidth(150)
        if CURRENT_USER_ROLE == "admin":
            self.btn_patient_admin.setObjectName("Primary")
        ctrl.addWidget(self.btn_patient_admin)

        root.addWidget(control_bar)

        # ── Signals ──
        self.btn_exercise.clicked.connect(self.select_exercise)
        self.btn_start.clicked.connect(self.toggle_start)
        self.btn_stop.clicked.connect(self.stop_process)
        self.btn_show_progress.clicked.connect(self.show_progress)
        self.btn_patient_admin.clicked.connect(self.open_patient_admin)

        # ── Start camera ──
        self.start_camera_thread()

    # ── Camera thread management ──────────────────────────────────────────────
    def start_camera_thread(self):
        if self.thread_cam is None:
            try:
                self.thread_cam = VisionCameraThread()
                self.thread_cam.use_webcam = True      # use live webcam
                self.thread_cam.process_enabled = False
                self.thread_cam.item = ""
                self.thread_cam.change_pixmap_signal.connect(self.update_image)
                self.thread_cam.stats_signal.connect(self.update_stats)
                self.thread_cam.side_reps_signal.connect(self.update_side_reps)
                self.thread_cam.say_signal.connect(self.tts_worker.enqueue)
                self.thread_cam.camera_status_signal.connect(self._on_camera_status)
                self.thread_cam.start()
                self.lbl_status.setText("Camera starting...")
                print("Vision camera thread started (webcam)")
            except Exception as e:
                print("Error starting camera thread:", e)
                self.lbl_status.setText(f"Camera error: {e}")
                self.thread_cam = None

    def stop_camera_thread(self):
        if self.thread_cam is not None:
            try:
                self.thread_cam.change_pixmap_signal.disconnect()
            except Exception:
                pass
            try:
                self.thread_cam.stop()
            except Exception as e:
                print("Error stopping camera thread:", e)
            self.thread_cam = None
            time.sleep(0.5)  # give camera time to release
            print("Vision camera thread stopped")

    @pyqtSlot(str)
    def _on_camera_status(self, status: str):
        print(f"Camera status: {status}")
        if status == "Camera OK":
            self.lbl_status.setText("Camera Active")
            self.feed_label.setText("")
        else:
            self.lbl_status.setText(status)
            self.feed_label.setText(status + "\nClick 'Camera Off' then 'Camera On' to retry")

    def toggle_camera_power(self):
        self.camera_on = not self.camera_on
        if self.camera_on:
            self.btn_cam_toggle.setText("Camera Off")
            self.feed_label.setText("Camera Feed")
            self.start_camera_thread()
            self.lbl_status.setText("Camera On")
        else:
            self.btn_cam_toggle.setText("Camera On")
            self.stop_camera_thread()
            self.feed_label.clear()
            self.feed_label.setText("Camera Off")
            self.lbl_status.setText("Camera Off")

    # ── Exercise selection & video playback ──────────────────────────────────
    def select_exercise(self):
        items = ("Squats", "Seated Knee Bending", "Straight Leg Raises")
        item, ok = QInputDialog.getItem(
            self, "Select Exercise", "Choose an exercise:", items, 0, False
        )
        if not (ok and item):
            return

        print(f"Exercise selected: {item}")
        self.lbl_status.setText(f"Exercise: {item}")
        self.session_exercise = item

        if self.thread_cam is None and self.camera_on:
            self.start_camera_thread()

        # Use patient's model video if available, otherwise fall back to built-in
        model_path = self._get_patient_model_video(item)
        if model_path:
            self.media_player.setSource(QUrl.fromLocalFile(str(Path(model_path).resolve())))
            self.media_player.play()
            self.lbl_status.setText(f"Exercise: {item}  ★ Patient model")
            print(f"Playing patient model video: {model_path}")
        else:
            video_map = {
                "Squats": Path("videos") / "squats.mp4",
                "Seated Knee Bending": Path("videos") / "Seated_Knee_Bending.mp4",
                "Straight Leg Raises": Path("videos") / "Straight_Leg_Raises.mp4",
            }
            self.play_instruction_video(video_map[item])

        if self.thread_cam is not None:
            self.thread_cam.item = item
            self.thread_cam.reset_exercise()

        # Reset session tracking for the new exercise
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0
        self.session_start_time = None
        self.session_left_correct = 0
        self.session_left_total = 0
        self.session_right_correct = 0
        self.session_right_total = 0
        self.lbl_reps.setText("—")
        self.lbl_knee_angle.setText("—")
        self.lbl_hip_angle.setText("—")
        self.lbl_left_reps.setText("—")
        self.lbl_right_reps.setText("—")

        # Show/hide left-right columns depending on exercise
        is_slr = (item == "Straight Leg Raises")
        self._left_col_widget.setVisible(is_slr)
        self._right_col_widget.setVisible(is_slr)

        self._activate_processing()

    def _on_leg_changed(self, text: str):
        leg_map = {"Auto": "auto", "Right Leg": "right", "Left Leg": "left"}
        value = leg_map.get(text, "auto")
        if self.thread_cam is not None:
            self.thread_cam.target_leg = value
        print(f"Target leg set to: {value}")

    def play_instruction_video(self, relative_path: Path):
        base_dir = Path(__file__).resolve().parent
        video_path = (base_dir / relative_path).resolve()
        if not video_path.exists():
            print("Video not found:", video_path)
            return
        self.media_player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.media_player.play()
        print("Playing video:", video_path)

    def _get_patient_model_video(self, exercise: str) -> str | None:
        """Return path to the patient's model video for this exercise, or None."""
        info = PATIENT_DATA_STORE.get("merged_info", {})
        pid = info.get("id", "").strip()
        if not pid:
            name = info.get("name", "").replace(" ", "_")
            pid = name if name else ""
        if not pid:
            return None
        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        if not json_path.exists():
            return None
        try:
            with open(json_path) as f:
                data = json.load(f)
            model = data.get("model_video", {})
            vpath = model.get("path", "")
            # Match if the exercise label starts with or equals the selected exercise
            model_ex = model.get("exercise", "")
            ex_match = (model_ex == exercise or
                        exercise in model_ex or model_ex in exercise)
            if ex_match and vpath and Path(vpath).exists():
                return vpath
        except Exception:
            pass
        return None

    def open_patient_search(self):
        """Open the patient search dialog and load a selected patient."""
        try:
            dlg = PatientSearchDialog(self)
            dlg.patient_loaded.connect(self._on_patient_loaded)
            dlg.exec()
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Could not open patient search:\n{e}")

    def _on_patient_loaded(self, data: dict):
        """Called when a patient is selected from the search dialog."""
        PATIENT_DATA_STORE["merged_info"] = data
        name = data.get("name", "").strip()
        pid  = data.get("id", "").strip()
        label = name if name else pid if pid else "Unknown"
        self.lbl_patient_badge.setText(f"Current Patient: {label}")

    def _on_media_error(self, err, err_str):
        print("Media player error:", err, err_str)

    # ── Processing controls ──────────────────────────────────────────────────
    def _activate_processing(self):
        self.is_running = True
        self.btn_start.setText("PAUSE")
        self.lbl_status.setText("Get ready — countdown starting…")
        if self.session_start_time is None:
            self.session_start_time = time.time()
        if self.thread_cam is not None:
            self.thread_cam.process_enabled = False
            self.thread_cam.countdown_state = "waiting"

    def toggle_start(self):
        if not self.is_running:
            if self.session_start_time is not None:
                # Resuming — skip countdown, go directly to tracking
                self.is_running = True
                self.btn_start.setText("PAUSE")
                self.lbl_status.setText("Tracking Active")
                if self.thread_cam is not None:
                    self.thread_cam.countdown_state = "idle"
                    self.thread_cam.process_enabled = True
            else:
                # First start — use countdown
                self._activate_processing()
        else:
            self.is_running = False
            self.btn_start.setText("RESUME")
            self.lbl_status.setText("Tracking Paused")
            if self.thread_cam is not None:
                self.thread_cam.process_enabled = False
                self.thread_cam.countdown_state = "idle"

    def stop_process(self):
        self.is_running = False
        self.btn_start.setText("START")
        self.lbl_status.setText("Session Stopped")
        if self.thread_cam is not None:
            self.thread_cam.process_enabled = False
            self.thread_cam.countdown_state = "idle"

        # Save session if it was actually running
        if self.session_start_time is not None and self.session_exercise:
            duration = time.time() - self.session_start_time
            now = datetime.now()
            session_data = {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "exercise": self.session_exercise,
                "duration_seconds": round(duration, 1),
                "correct_reps": self.session_correct_reps,
                "total_reps": self.session_total_reps,
                "min_knee_angle": round(
                    self.session_min_knee if self.session_min_knee != float("inf") else 0, 1
                ),
                "max_knee_angle": round(self.session_max_knee, 1),
            }
            # Include per-side data for Straight Leg Raises
            if self.session_exercise == "Straight Leg Raises":
                session_data["left_correct_reps"] = self.session_left_correct
                session_data["left_total_reps"] = self.session_left_total
                session_data["right_correct_reps"] = self.session_right_correct
                session_data["right_total_reps"] = self.session_right_total
            SessionManager.save(session_data)

        # Reset session state
        self.session_start_time = None
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0
        self.session_left_correct = 0
        self.session_left_total = 0
        self.session_right_correct = 0
        self.session_right_total = 0

        self.lbl_reps.setText("—")
        self.lbl_knee_angle.setText("—")
        self.lbl_hip_angle.setText("—")
        self.lbl_left_reps.setText("—")
        self.lbl_right_reps.setText("—")
        try:
            self.media_player.stop()
        except Exception:
            pass

    # ── Patient Dashboard / My Profile ───────────────────────────────────────
    def open_patient_admin(self):
        if CURRENT_USER_ROLE == "admin":
            # Full admin dashboard — pause camera first
            if self.thread_cam is not None:
                try:
                    self.thread_cam.change_pixmap_signal.disconnect()
                except Exception:
                    pass
                self.thread_cam.stop()
                self.thread_cam = None

            data = PATIENT_DATA_STORE.get("merged_info", {})
            dashboard = PatientDashboard(self)
            if data:
                dashboard._load_patient(data)
            dashboard.exec()

            # Resume camera
            if self.camera_on:
                self.start_camera_thread()
                if self.is_running and self.thread_cam is not None:
                    self.thread_cam.process_enabled = True
        else:
            # Patient — read-only profile
            dlg = PatientDashboardLite(self)
            dlg.exec()

    # ── Progress / Reports ────────────────────────────────────────────────────
    def show_progress(self):
        if CURRENT_USER_ROLE == "admin":
            # Admin: open PatientDashboard directly on the Reports tab
            if self.thread_cam is not None:
                try:
                    self.thread_cam.change_pixmap_signal.disconnect()
                except Exception:
                    pass
                self.thread_cam.stop()
                self.thread_cam = None
            data = PATIENT_DATA_STORE.get("merged_info", {})
            dashboard = PatientDashboard(self)
            if data:
                dashboard._load_patient(data)
            dashboard.list_widget.setCurrentRow(PatientDashboard.PAGE_REPORTS)
            dashboard.exec()
            if self.camera_on:
                self.start_camera_thread()
                if self.is_running and self.thread_cam is not None:
                    self.thread_cam.process_enabled = True
        else:
            dlg = ProgressDialog(self)
            dlg.exec()

    # ── Stats update ──────────────────────────────────────────────────────────
    @pyqtSlot(int, int, float, float)
    def update_stats(self, correct_reps: int, total_reps: int, knee: float, hip: float):
        self.session_correct_reps = correct_reps
        self.session_total_reps = total_reps
        if knee > 0:
            self.session_min_knee = min(self.session_min_knee, knee)
            self.session_max_knee = max(self.session_max_knee, knee)
        self.lbl_reps.setText(f"{correct_reps}/{total_reps}")
        self.lbl_knee_angle.setText(f"{knee:.1f}")
        self.lbl_hip_angle.setText(f"{hip:.1f}" if hip > 0 else "—")

    @pyqtSlot(int, int, int, int)
    def update_side_reps(self, left_correct: int, left_total: int,
                         right_correct: int, right_total: int):
        self.session_left_correct = left_correct
        self.session_left_total = left_total
        self.session_right_correct = right_correct
        self.session_right_total = right_total
        self.lbl_left_reps.setText(f"{left_correct}/{left_total}")
        self.lbl_right_reps.setText(f"{right_correct}/{right_total}")

    # ── Frame update ─────────────────────────────────────────────────────────
    @pyqtSlot(QImage)
    def update_image(self, qt_img: QImage):
        if not self.camera_on:
            return
        pixmap = QPixmap.fromImage(qt_img)
        scaled = pixmap.scaled(
            self.feed_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.feed_label.setPixmap(scaled)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self.stop_camera_thread()
        self.tts_worker.stop()
        try:
            self.media_player.stop()
        except Exception:
            pass
        event.accept()


# ─────────────────────────── ADMIN PATIENT BROWSER ──────────────────────────
class AdminPatientBrowser(QDialog):
    """Doctor's first screen: searchable list of all patients.
    Double-click (or click Open Profile) to open PatientDashboard for that patient."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KneeConnect — Patient Browser (Admin)")
        self.setWindowIcon(create_app_icon())
        self.resize(760, 560)

        self._all_patients: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Header row: title + new patient button
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(HeaderLabel("PATIENT BROWSER"))
        hdr_row.addStretch()
        btn_new = QPushButton("+ New Patient")
        btn_new.setObjectName("Primary")
        btn_new.setFixedSize(140, 36)
        btn_new.clicked.connect(self._create_new_patient)
        hdr_row.addWidget(btn_new)
        root.addLayout(hdr_row)

        # Search box
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by name, ID, surgeon or physio…")
        self._search.textChanged.connect(self._filter)
        root.addWidget(self._search)

        # Patient list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(
            "QListWidget { alternate-background-color: #333; } "
            "QListWidget::item { padding: 10px; border-radius: 4px; } "
        )
        self._list.itemDoubleClicked.connect(self._open_selected)
        self._list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self._list, stretch=1)

        # Detail strip
        self._lbl_detail = QLabel("")
        self._lbl_detail.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        )
        root.addWidget(self._lbl_detail)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_open = QPushButton("Open Profile")
        self._btn_open.setObjectName("Primary")
        self._btn_open.setFixedSize(160, 40)
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(self._btn_open)

        btn_exit = QPushButton("Exit Application")
        btn_exit.setFixedSize(140, 40)
        btn_exit.clicked.connect(self.reject)
        btn_row.addWidget(btn_exit)
        root.addLayout(btn_row)

        self._load_patients()

    # ── Data ─────────────────────────────────────────────────────────────────
    def _load_patients(self):
        patients: list[dict] = []
        seen: set[str] = set()
        assets_dir = Path(PATIENT_ASSETS_FOLDER)
        if assets_dir.exists():
            for subdir in sorted(assets_dir.iterdir()):
                if subdir.is_dir():
                    jp = subdir / "patient.json"
                    if jp.exists():
                        try:
                            with open(jp) as f:
                                data = json.load(f)
                            data["_source"] = str(jp)
                            patients.append(data)
                            seen.add(data.get("name", "").lower())
                        except Exception:
                            pass
        for jp in sorted(Path(".").glob("*.json")):
            if jp.name.endswith("_sessions.json") or jp.name == "unknown_sessions.json":
                continue
            try:
                with open(jp) as f:
                    data = json.load(f)
                name = data.get("name", "").lower()
                if "name" in data and name not in seen:
                    data["_source"] = str(jp)
                    patients.append(data)
            except Exception:
                pass
        patients.sort(key=lambda d: d.get("name", "").lower())
        self._all_patients = patients
        self._filter(self._search.text())

    def _filter(self, text: str):
        q = text.strip().lower()
        self._shown: list[dict] = [
            p for p in self._all_patients
            if not q
            or q in p.get("name","").lower()
            or q in str(p.get("id","")).lower()
            or q in p.get("surgeon","").lower()
            or q in p.get("physio","").lower()
        ]
        self._list.clear()
        for p in self._shown:
            name = p.get("name", "—")
            pid  = p.get("id", "")
            age  = p.get("age", "")
            surgeon = p.get("surgeon", "")
            parts = [name]
            if pid:     parts.append(f"ID: {pid}")
            if age:     parts.append(f"Age: {age}")
            if surgeon: parts.append(f"Surgeon: {surgeon}")
            self._list.addItem("   |   ".join(parts))
        self._btn_open.setEnabled(self._list.count() > 0)
        self._lbl_detail.setText(f"{len(self._shown)} patient(s)")

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._shown):
            p = self._shown[row]
            parts = []
            if p.get("mobile"):       parts.append(f"Mobile: {p['mobile']}")
            if p.get("surgery_date"): parts.append(f"Surgery: {p['surgery_date']}")
            if p.get("physio"):       parts.append(f"Physio: {p['physio']}")
            if p.get("height") or p.get("weight"):
                parts.append(f"H/W: {p.get('height','?')}cm / {p.get('weight','?')}kg")
            self._lbl_detail.setText("  |  ".join(parts) if parts else "")
            self._btn_open.setEnabled(True)

    def _open_selected(self):
        row = self._list.currentRow()
        if not (0 <= row < len(self._shown)):
            return
        data = self._shown[row]
        PATIENT_DATA_STORE["merged_info"] = data

        dashboard = PatientDashboard(self)
        dashboard._load_patient(data)        # pre-load the patient into all pages
        dashboard.exec()

        # Refresh list in case data changed
        self._load_patients()

    def _create_new_patient(self):
        dashboard = PatientDashboard(self)
        dashboard.exec()
        self._load_patients()


# ─────────────────────────── PATIENT DASHBOARD LITE ─────────────────────────
class PatientDashboardLite(QDialog):
    """Read-only profile + session history for a logged-in patient."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("My Profile")
        self.setWindowIcon(create_app_icon())
        self.resize(920, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        wrapper = QHBoxLayout()
        wrapper.setSpacing(0)

        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-right: 1px solid #444;"
        )
        sidebar.setFixedWidth(200)
        sl = QVBoxLayout(sidebar)
        sl.setSpacing(8)
        sl.addWidget(HeaderLabel("MY PROFILE"))

        self._list = QListWidget()
        self._list.addItems(["My Info", "Session History"])
        self._list.setCurrentRow(0)
        self._list.setFixedHeight(120)
        self._list.currentRowChanged.connect(self._on_nav)
        sl.addWidget(self._list)
        sl.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setStyleSheet("background-color: #555;")
        btn_close.clicked.connect(self.accept)
        sl.addWidget(btn_close)
        wrapper.addWidget(sidebar)

        # Content
        content = QFrame()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)

        self._stack = QStackedWidget()

        # Page 0: My Info (read-only)
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.addWidget(SubHeaderLabel("Patient Information"))
        grid = QGridLayout()
        grid.setSpacing(12)
        self._info_fields: dict[str, QLabel] = {}
        field_defs = [
            ("Name", "name"), ("Patient ID", "id"), ("Age", "age"),
            ("Mobile", "mobile"), ("Gender", "gender"),
            ("Surgeon", "surgeon"), ("Physiotherapist", "physio"),
            ("Height (cm)", "height"), ("Weight (kg)", "weight"),
            ("Surgery Date", "surgery_date"),
        ]
        for i, (label, key) in enumerate(field_defs):
            r, c = divmod(i, 2)
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; border: none;")
            val = QLabel("—")
            val.setStyleSheet("color: white; border: none; font-weight: bold;")
            grid.addWidget(lbl, r, c * 2)
            grid.addWidget(val, r, c * 2 + 1)
            self._info_fields[key] = val
        info_layout.addLayout(grid)

        # Extra text fields
        for label, key in [
            ("Functional Goals", "goals"),
            ("Medical History", "history"),
        ]:
            info_layout.addWidget(QLabel(f"{label}:"))
            val_lbl = QLabel("—")
            val_lbl.setWordWrap(True)
            val_lbl.setStyleSheet(
                f"color: {ModernTheme.TEXT_GRAY}; border: 1px solid #444; "
                "border-radius: 4px; padding: 6px; background: #222;"
            )
            self._info_fields[key] = val_lbl
            info_layout.addWidget(val_lbl)

        info_layout.addStretch()
        self._stack.addWidget(info_widget)

        # Page 1: Session History (reuse PatientHistoryPage)
        self._history = PatientHistoryPage()
        self._stack.addWidget(self._history)

        cl.addWidget(self._stack)
        wrapper.addWidget(content)
        root.addLayout(wrapper)

        self._populate()

    def _on_nav(self, row: int):
        self._stack.setCurrentIndex(row)

    def _populate(self):
        data = PATIENT_DATA_STORE.get("merged_info", {})
        for key, lbl in self._info_fields.items():
            val = str(data.get(key, "") or "—")
            lbl.setText(val)
        self._history.load_patient(data)


# ─────────────────────────── ROLE SELECTION ──────────────────────────────────
class RoleSelectionDialog(QDialog):
    PATIENT = 1
    DOCTOR  = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("KneeConnect — Select Role")
        self.setWindowIcon(create_app_icon())
        self.setFixedSize(640, 420)
        self._role = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        layout.addWidget(HeaderLabel("WHO ARE YOU?"))

        sub = QLabel("Select your role to continue")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 13px; border: none;")
        layout.addWidget(sub)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(24)

        # Patient card
        p_card = QFrame()
        p_card.setObjectName("Card")
        pl = QVBoxLayout(p_card)
        pl.setSpacing(10)
        pl.setContentsMargins(24, 20, 24, 20)
        lbl_pi = QLabel("🧑‍🦽")
        lbl_pi.setStyleSheet("font-size: 52px; border: none;")
        lbl_pi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(lbl_pi)
        lbl_pt = QLabel("PATIENT")
        lbl_pt.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 20px; "
            "font-weight: bold; border: none;"
        )
        lbl_pt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl.addWidget(lbl_pt)
        lbl_pd = QLabel("Enter your Patient ID to\nstart your exercise session")
        lbl_pd.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;")
        lbl_pd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_pd.setWordWrap(True)
        pl.addWidget(lbl_pd)
        btn_p = QPushButton("Enter as Patient")
        btn_p.setObjectName("Primary")
        btn_p.setFixedHeight(42)
        btn_p.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_p.clicked.connect(lambda: self._choose(self.PATIENT))
        pl.addWidget(btn_p)
        cards_row.addWidget(p_card)

        # Doctor card
        d_card = QFrame()
        d_card.setObjectName("Card")
        dl = QVBoxLayout(d_card)
        dl.setSpacing(10)
        dl.setContentsMargins(24, 20, 24, 20)
        lbl_di = QLabel("👨‍⚕️")
        lbl_di.setStyleSheet("font-size: 52px; border: none;")
        lbl_di.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(lbl_di)
        lbl_dt = QLabel("DOCTOR / PHYSIO")
        lbl_dt.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 20px; "
            "font-weight: bold; border: none;"
        )
        lbl_dt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(lbl_dt)
        lbl_dd = QLabel("Search patients, manage profiles,\nprescribe exercises & view progress")
        lbl_dd.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;")
        lbl_dd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_dd.setWordWrap(True)
        dl.addWidget(lbl_dd)
        btn_d = QPushButton("Enter as Doctor")
        btn_d.setObjectName("Primary")
        btn_d.setFixedHeight(42)
        btn_d.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_d.clicked.connect(lambda: self._choose(self.DOCTOR))
        dl.addWidget(btn_d)
        cards_row.addWidget(d_card)

        layout.addLayout(cards_row)

    def _choose(self, role: int):
        if role == self.DOCTOR:
            pwd, ok = QInputDialog.getText(
                self, "Doctor / Admin Access",
                "Enter access password:", QLineEdit.EchoMode.Password
            )
            if not ok:
                return
            if pwd != "1234":
                QMessageBox.warning(self, "Access Denied",
                                    "Incorrect password.\n(Default: 1234)")
                return
        self._role = role
        self.accept()

    def chosen_role(self) -> int:
        return self._role


# ─────────────────────────── PATIENT LOGIN ───────────────────────────────────
class PatientLoginDialog(QDialog):
    """Patient enters their ID to find and load their profile."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Patient Login")
        self.setWindowIcon(create_app_icon())
        self.setFixedSize(520, 440)
        self._patient_data: dict | None = None
        self._all_patients: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 24)
        layout.setSpacing(14)
        layout.addWidget(HeaderLabel("PATIENT LOGIN"))

        instr = QLabel("Enter your Patient ID to access your profile and exercises:")
        instr.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; border: none;")
        instr.setWordWrap(True)
        layout.addWidget(instr)

        id_row = QHBoxLayout()
        self._id_input = QLineEdit()
        self._id_input.setPlaceholderText("Patient ID  (e.g.  P001 / 12345)")
        self._id_input.setFixedHeight(44)
        self._id_input.setStyleSheet("font-size: 16px; padding: 4px 12px;")
        self._id_input.textChanged.connect(self._clear_result)
        self._id_input.returnPressed.connect(self._search)
        id_row.addWidget(self._id_input)
        btn_search = QPushButton("Search")
        btn_search.setObjectName("Primary")
        btn_search.setFixedSize(90, 44)
        btn_search.clicked.connect(self._search)
        id_row.addWidget(btn_search)
        layout.addLayout(id_row)

        # Found patient info card
        self._result_frame = QFrame()
        self._result_frame.setObjectName("Card")
        self._result_frame.setVisible(False)
        rl = QVBoxLayout(self._result_frame)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(6)
        self._lbl_found_name = QLabel()
        self._lbl_found_name.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 17px; "
            "font-weight: bold; border: none;"
        )
        self._lbl_found_details = QLabel()
        self._lbl_found_details.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;"
        )
        self._lbl_found_details.setWordWrap(True)
        rl.addWidget(self._lbl_found_name)
        rl.addWidget(self._lbl_found_details)
        layout.addWidget(self._result_frame)

        # Not-found message
        self._lbl_not_found = QLabel("⚠  No patient found with that ID. Please check and try again.")
        self._lbl_not_found.setStyleSheet("color: #e74c3c; border: none;")
        self._lbl_not_found.setWordWrap(True)
        self._lbl_not_found.setVisible(False)
        layout.addWidget(self._lbl_not_found)

        layout.addStretch()

        self._btn_start = QPushButton("▶  Start Exercise Session")
        self._btn_start.setFixedHeight(52)
        self._btn_start.setEnabled(False)
        self._btn_start.setStyleSheet(
            "background-color: #3a3a3a; color: #666; border-radius: 10px; "
            "font-size: 15px; font-weight: bold;"
        )
        self._btn_start.clicked.connect(self.accept)
        layout.addWidget(self._btn_start)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

        self._scan_patients()

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _scan_patients(self):
        """Load all patient records from disk for fast ID lookup."""
        patients: list[dict] = []
        seen: set[str] = set()
        assets_dir = Path(PATIENT_ASSETS_FOLDER)
        if assets_dir.exists():
            for subdir in sorted(assets_dir.iterdir()):
                if subdir.is_dir():
                    jp = subdir / "patient.json"
                    if jp.exists():
                        try:
                            with open(jp) as f:
                                data = json.load(f)
                            data["_source"] = str(jp)
                            patients.append(data)
                            seen.add(data.get("name", "").lower())
                        except Exception:
                            pass
        for jp in sorted(Path(".").glob("*.json")):
            if jp.name.endswith("_sessions.json") or jp.name == "unknown_sessions.json":
                continue
            try:
                with open(jp) as f:
                    data = json.load(f)
                name = data.get("name", "").lower()
                if "name" in data and name not in seen:
                    data["_source"] = str(jp)
                    patients.append(data)
            except Exception:
                pass
        self._all_patients = patients

    def _clear_result(self):
        self._result_frame.setVisible(False)
        self._lbl_not_found.setVisible(False)
        self._patient_data = None
        self._btn_start.setEnabled(False)
        self._btn_start.setStyleSheet(
            "background-color: #3a3a3a; color: #666; border-radius: 10px; "
            "font-size: 15px; font-weight: bold;"
        )

    def _search(self):
        query = self._id_input.text().strip().lower()
        if not query:
            return
        found = None
        for p in self._all_patients:
            if str(p.get("id", "")).strip().lower() == query:
                found = p
                break
        if not found:
            self._result_frame.setVisible(False)
            self._lbl_not_found.setVisible(True)
            return
        self._patient_data = found
        self._lbl_not_found.setVisible(False)
        name = found.get("name", "Unknown")
        parts = []
        if found.get("age"):    parts.append(f"Age: {found['age']}")
        if found.get("surgeon"): parts.append(f"Surgeon: {found['surgeon']}")
        if found.get("physio"):  parts.append(f"Physiotherapist: {found['physio']}")
        self._lbl_found_name.setText(f"✓  {name}")
        self._lbl_found_details.setText("   |   ".join(parts) if parts else "Profile found.")
        self._result_frame.setVisible(True)
        self._btn_start.setEnabled(True)
        self._btn_start.setStyleSheet(
            f"background-color: {ModernTheme.ACCENT_PRIMARY}; color: white; "
            "border-radius: 10px; font-size: 15px; font-weight: bold;"
        )

    def get_patient_data(self) -> dict | None:
        return self._patient_data


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ModernTheme.STYLESHEET)
    app.setWindowIcon(create_app_icon())

    # ── Step 1: Terms of Service ──────────────────────────────────────────────
    terms = TermsDialog()
    terms.show()
    terms.raise_()
    terms.activateWindow()
    if terms.exec() != QDialog.DialogCode.Accepted:
        sys.exit()

    # ── Step 2: Role selection ────────────────────────────────────────────────
    role_dlg = RoleSelectionDialog()
    role_dlg.show()
    role_dlg.raise_()
    role_dlg.activateWindow()
    if role_dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit()

    role = role_dlg.chosen_role()

    # ── Doctor / Physiotherapist path ─────────────────────────────────────────
    if role == RoleSelectionDialog.DOCTOR:
        CURRENT_USER_ROLE = "admin"  # module-level, no global declaration needed here
        # Show the patient browser immediately — one-click access to all patients
        browser = AdminPatientBrowser()
        browser.show()
        browser.raise_()
        browser.activateWindow()
        sys.exit(app.exec())

    # ── Patient path ──────────────────────────────────────────────────────────
    login_dlg = PatientLoginDialog()
    login_dlg.show()
    login_dlg.raise_()
    login_dlg.activateWindow()
    if login_dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit()

    patient_data = login_dlg.get_patient_data()
    if patient_data:
        PATIENT_DATA_STORE["merged_info"] = patient_data

    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())
