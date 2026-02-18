import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

from vision_thread import CameraThread as VisionCameraThread

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QInputDialog, QDialog,
    QCheckBox, QTextEdit, QLineEdit, QFormLayout, QComboBox,
    QMessageBox, QScrollArea, QStackedWidget, QListWidget, QGroupBox,
    QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtGui import QImage, QPixmap, QIcon, QFont, QColor, QPainter, QPen, QBrush

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

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


# ─────────────────────────── GLOBAL DATA ──────────────────────────────────────
PATIENT_DATA_STORE = {
    "merged_info": {}, "exercise_schedule": {}, "consent": {},
    "progress": {}, "setup_videos": []
}


# ─────────────────────────── SESSION MANAGER ──────────────────────────────────
class SessionManager:
    @staticmethod
    def _session_file():
        info = PATIENT_DATA_STORE.get("merged_info", {})
        name = info.get("name", "unknown").replace(" ", "_")
        return f"{name}_sessions.json"

    @classmethod
    def save(cls, session: dict):
        path = cls._session_file()
        sessions = cls.load()
        sessions.append(session)
        try:
            with open(path, "w") as f:
                json.dump(sessions, f, indent=2)
        except Exception as e:
            print("SessionManager.save error:", e)

    @classmethod
    def load(cls) -> list:
        path = cls._session_file()
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []


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
    """Basic webcam thread (no pose processing) used by SetupPage."""
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        cap = cv2.VideoCapture(0)
        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.change_pixmap_signal.emit(qt_img)
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

        layout.addWidget(HeaderLabel("TERMS OF SERVICE"))

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFrameShape(QFrame.Shape.NoFrame)
        self.text_area.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; padding: 10px; border-radius: 8px;"
        )
        self.text_area.setHtml(
            "<h3>KNEE CONNECT SOFTWARE LICENSE</h3>"
            "<p>Last Updated: 2024</p><br>"
            "<p><b>1. Acceptance:</b> By accessing this application, you confirm that you are "
            "an authorized medical professional.</p>"
            "<p><b>2. Data Privacy:</b> All patient data entered is stored locally in memory "
            "during this session. Ensure compliance with GDPR/HIPAA when exporting externally.</p>"
            "<p><b>3. Safety Disclaimer:</b> This computer vision tool is an aid, not a "
            "replacement for professional diagnosis. Always verify range-of-motion metrics manually.</p>"
            "<p><b>4. Liability:</b> The developers accept no liability for injury or misdiagnosis "
            "resulting from misuse of this software.</p>"
            "<br><br><p><i>Scroll to the bottom to agree.</i></p>"
        )
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
        layout = QVBoxLayout(self)

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
                shady = "color: #999; background-color: #222; border: 1px solid #444;"
                for w in self._all_editable_fields():
                    w.setStyleSheet(shady)
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
            QMessageBox.information(self, "Success", f"Patient record saved to {filename}.")
            normal = "color: white; background-color: #222; border: 1px solid #555;"
            for w in self._all_editable_fields():
                w.setStyleSheet(normal)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file: {e}")


# ─────────────────────────── SETUP / VIDEO PAGE ───────────────────────────────
class VideoSlotWidget(QFrame):
    def __init__(self, index, image=None):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedSize(160, 140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.img_lbl = QLabel()
        self.img_lbl.setStyleSheet("background-color: black; border-radius: 4px;")
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if image:
            self.img_lbl.setPixmap(
                QPixmap.fromImage(image).scaled(150, 100, Qt.AspectRatioMode.KeepAspectRatio)
            )
        else:
            self.img_lbl.setText(f"Empty Slot {index}")
        layout.addWidget(self.img_lbl)

        self.chk = QCheckBox(f"Video {index}")
        layout.addWidget(self.chk)


class SetupPage(QWidget):
    def __init__(self):
        super().__init__()
        self.main_layout = QHBoxLayout(self)
        self.video_slots = []
        self.recording = False
        self.current_frame = None

        # --- LEFT PANEL ---
        left_panel = QWidget()
        left_panel.setFixedWidth(250)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        left_layout.addWidget(QLabel("Select Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Option 1 (Standard)", "Option 2 (Advanced)",
            "Option 3 (AI)", "Option 4 (Manual)"
        ])
        left_layout.addWidget(self.method_combo)
        left_layout.addSpacing(15)
        left_layout.addWidget(SubHeaderLabel("Videos"))

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.video_container = QWidget()
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.setSpacing(10)
        self.video_layout.addStretch()
        self.scroll_area.setWidget(self.video_container)
        left_layout.addWidget(self.scroll_area)

        self.btn_save_setup = QPushButton("Save")
        self.btn_save_setup.clicked.connect(
            lambda: QMessageBox.information(self, "Saved", "Setup Configuration Saved")
        )
        self.btn_init = QPushButton("Initialize")
        self.btn_init.setEnabled(False)
        self.btn_init.clicked.connect(self.initialize_videos)

        left_layout.addWidget(self.btn_save_setup)
        left_layout.addWidget(self.btn_init)
        self.main_layout.addWidget(left_panel)

        # --- CENTER PANEL ---
        center_panel = QVBoxLayout()

        angle_grid = QGridLayout()
        angle_grid.setSpacing(10)
        self.angle_vars = []
        self.angle_inputs = []

        for i in range(4):
            title = QLabel(f"Angle {i + 1}")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(
                f"color: {ModernTheme.ACCENT_PRIMARY}; font-weight: bold;"
            )
            angle_grid.addWidget(title, 0, i)

            var_lbl = QLabel("0.0")
            var_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            var_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
            self.angle_vars.append(var_lbl)
            angle_grid.addWidget(var_lbl, 1, i)

            inp = QLineEdit()
            inp.setPlaceholderText("#")
            inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp.setFixedWidth(80)
            self.angle_inputs.append(inp)

            container = QWidget()
            cl = QHBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addStretch()
            cl.addWidget(inp)
            cl.addStretch()
            angle_grid.addWidget(container, 2, i)

        center_panel.addLayout(angle_grid)
        center_panel.addSpacing(15)

        self.cam_frame = CameraDisplayWidget("Camera Offline")
        center_panel.addWidget(self.cam_frame)

        self.btn_rec = QPushButton("START")
        self.btn_rec.setObjectName("Success")
        self.btn_rec.setFixedSize(200, 50)
        self.btn_rec.clicked.connect(self.toggle_recording)
        center_panel.addWidget(self.btn_rec, alignment=Qt.AlignmentFlag.AlignCenter)

        self.main_layout.addLayout(center_panel)
        self.thread: SimpleCameraThread | None = None

    def start_camera(self):
        if self.thread is None:
            self.thread = SimpleCameraThread()
            self.thread.change_pixmap_signal.connect(self.update_image)
            self.thread.start()

    def stop_camera(self):
        if self.thread:
            try:
                self.thread.change_pixmap_signal.disconnect()
            except Exception:
                pass
            self.thread.stop()
            self.thread = None

    @pyqtSlot(QImage)
    def update_image(self, qt_img):
        self.current_frame = qt_img
        self.cam_frame.set_image(qt_img)

    def toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.btn_rec.setText("STOP")
            self.btn_rec.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_DANGER}; color: white; "
                "font-weight: bold; border-radius: 6px; padding: 8px;"
            )
        else:
            self.recording = False
            self.btn_rec.setText("START")
            self.btn_rec.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_SUCCESS}; color: white; "
                "font-weight: bold; border-radius: 6px; padding: 8px;"
            )
            self.add_recorded_video()

    def add_recorded_video(self):
        idx = len(self.video_slots) + 1
        slot = VideoSlotWidget(idx, self.current_frame)
        slot.chk.stateChanged.connect(self.check_selection)
        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
        self.video_slots.append(slot)

    def check_selection(self):
        any_checked = any(s.chk.isChecked() for s in self.video_slots)
        self.btn_init.setEnabled(any_checked)
        if any_checked:
            self.btn_init.setStyleSheet(
                f"background-color: {ModernTheme.ACCENT_PRIMARY}; color: white;"
            )
        else:
            self.btn_init.setStyleSheet("background-color: #444; color: #777;")

    def initialize_videos(self):
        count = sum(1 for s in self.video_slots if s.chk.isChecked())
        QMessageBox.information(
            self, "Initialized", f"{count} video(s) initialized and saved to the program."
        )


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


# ─────────────────────────── PATIENT DASHBOARD ───────────────────────────────
class PatientDashboard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Patient Management Dashboard")
        self.setWindowIcon(create_app_icon())
        self.resize(1000, 700)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-right: 1px solid #444;"
        )
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(HeaderLabel("MENU"))

        self.list_widget = QListWidget()
        self.list_widget.addItems([
            "Merged Information",
            "Setup",
            "Exercise Schedule",
            "Consent Form",
            "Progress Report",
        ])
        self.list_widget.setCurrentRow(0)
        self.list_widget.currentRowChanged.connect(self.display_page)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setFixedHeight(400)
        sidebar_layout.addWidget(self.list_widget)
        sidebar_layout.addStretch()

        btn_back = QPushButton("Back to Camera")
        btn_back.setStyleSheet("background-color: #555;")
        btn_back.setAutoDefault(False)   # prevent Enter key from closing dialog
        btn_back.setDefault(False)
        btn_back.clicked.connect(self.accept)
        sidebar_layout.addWidget(btn_back)
        main_layout.addWidget(sidebar)

        # Content area
        content_area = QFrame()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.stack = QStackedWidget()
        self.stack.addWidget(MergedPatientForm())

        self.setup_page = SetupPage()
        self.stack.addWidget(self.setup_page)

        self.stack.addWidget(ExerciseForm())

        consent_widget = QWidget()
        cl = QVBoxLayout(consent_widget)
        cl.addWidget(SubHeaderLabel("Patient Consent"))
        btn_upload = QPushButton("Upload Consent PDF / Image")
        cl.addWidget(btn_upload)
        cl.addWidget(QLabel("Description:"))
        desc = QTextEdit()
        cl.addWidget(desc)
        btn_save_c = QPushButton("Save")
        btn_save_c.setObjectName("Primary")
        cl.addWidget(btn_save_c, alignment=Qt.AlignmentFlag.AlignRight)
        cl.addStretch()
        self.stack.addWidget(consent_widget)

        self.stack.addWidget(GenericFormWidget("Progress Report", [
            ("Changes in Pain / Function", "area"),
            ("Range of Motion Improvement", "area"),
        ], "progress"))

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_area)

    def display_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.setup_page.start_camera()
        else:
            self.setup_page.stop_camera()

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

        sessions = SessionManager.load()
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
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Date & Time", "Exercise", "Duration",
            "Correct Reps", "Total Reps",
            "Min Angle (\u00b0)", "Max Angle (\u00b0)",
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setRowCount(len(sessions))
        for row, s in enumerate(reversed(sessions)):
            dur = s.get("duration_seconds", 0)
            dur_str = f"{int(dur // 60)}m {int(dur % 60)}s"
            for col, val in enumerate([
                s.get("date", "") + "  " + s.get("time", ""),
                s.get("exercise", ""),
                dur_str,
                str(s.get("correct_reps", 0)),
                str(s.get("total_reps", 0)),
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

        # ── Session tracking ──
        self.session_start_time: float | None = None
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0
        self.session_exercise = ""

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

        stats_bar.addStretch()
        stats_bar.addLayout(reps_col)
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

        self.btn_show_progress = QPushButton("Show Progress")
        self.btn_show_progress.setFixedWidth(130)
        ctrl.addWidget(self.btn_show_progress)

        self.btn_patient_admin = QPushButton("Patient Admin")
        self.btn_patient_admin.setFixedWidth(130)
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
                self.thread_cam.start()
                print("Vision camera thread started (webcam)")
            except Exception as e:
                print("Error starting camera thread:", e)
                self.thread_cam = None

    def stop_camera_thread(self):
        if self.thread_cam is not None:
            try:
                self.thread_cam.stop()
            except Exception as e:
                print("Error stopping camera thread:", e)
            self.thread_cam = None
            print("Vision camera thread stopped")

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

        video_map = {
            "Squats": Path("videos") / "squats.mp4",
            "Seated Knee Bending": Path("videos") / "Seated_Knee_Bending.mp4",
            "Straight Leg Raises": Path("videos") / "Straight_Leg_Raises.mp4",
        }
        self.play_instruction_video(video_map[item])

        if self.thread_cam is not None:
            self.thread_cam.item = item

        self._activate_processing()

    def play_instruction_video(self, relative_path: Path):
        base_dir = Path(__file__).resolve().parent
        video_path = (base_dir / relative_path).resolve()
        if not video_path.exists():
            print("Video not found:", video_path)
            return
        self.media_player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.media_player.play()
        print("Playing video:", video_path)

    def _on_media_error(self, err, err_str):
        print("Media player error:", err, err_str)

    # ── Processing controls ──────────────────────────────────────────────────
    def _activate_processing(self):
        self.is_running = True
        self.btn_start.setText("PAUSE")
        self.lbl_status.setText("Tracking Active")
        if self.session_start_time is None:
            self.session_start_time = time.time()
        if self.thread_cam is not None:
            self.thread_cam.process_enabled = True

    def toggle_start(self):
        if not self.is_running:
            self._activate_processing()
        else:
            self.is_running = False
            self.btn_start.setText("RESUME")
            self.lbl_status.setText("Tracking Paused")
            if self.thread_cam is not None:
                self.thread_cam.process_enabled = False

    def stop_process(self):
        self.is_running = False
        self.btn_start.setText("START")
        self.lbl_status.setText("Session Stopped")
        if self.thread_cam is not None:
            self.thread_cam.process_enabled = False

        # Save session if it was actually running
        if self.session_start_time is not None and self.session_exercise:
            duration = time.time() - self.session_start_time
            now = datetime.now()
            SessionManager.save({
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
            })

        # Reset session state
        self.session_start_time = None
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0

        self.lbl_reps.setText("—")
        self.lbl_knee_angle.setText("—")
        self.lbl_hip_angle.setText("—")
        try:
            self.media_player.stop()
        except Exception:
            pass

    # ── Patient Admin (password-protected) ───────────────────────────────────
    def open_patient_admin(self):
        pwd, ok = QInputDialog.getText(
            self, "Admin Access", "Enter Password:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if pwd != "1234":
            QMessageBox.warning(self, "Access Denied", "Incorrect password.")
            return

        # Pause camera while dashboard is open
        if self.thread_cam is not None:
            try:
                self.thread_cam.change_pixmap_signal.disconnect()
            except Exception:
                pass
            self.thread_cam.stop()
            self.thread_cam = None

        dashboard = PatientDashboard(self)
        dashboard.exec()

        # Resume camera
        if self.camera_on:
            self.start_camera_thread()
            if self.is_running and self.thread_cam is not None:
                self.thread_cam.process_enabled = True

    # ── Progress report ───────────────────────────────────────────────────────
    def show_progress(self):
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
        try:
            self.media_player.stop()
        except Exception:
            pass
        event.accept()


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ModernTheme.STYLESHEET)
    app.setWindowIcon(create_app_icon())

    terms = TermsDialog()
    terms.show()
    terms.raise_()
    terms.activateWindow()
    if terms.exec() == QDialog.DialogCode.Accepted:
        window = MainWindow()
        window.show()
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec())
    else:
        sys.exit()
