import os
import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSizePolicy, QLineEdit, QTextEdit, QComboBox, QFormLayout,
    QMessageBox, QScrollArea, QGroupBox, QGridLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QSpinBox, QInputDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSlot, QDate
from PyQt6.QtGui import QImage, QPixmap, QDoubleValidator, QFont

from theme import ModernTheme
from constants import (
    PATIENT_ASSETS_FOLDER, PATIENT_DATA_STORE,
    canonical_exercise, create_app_icon,
)
from widgets import (
    HeaderLabel, SubHeaderLabel, CameraDisplayWidget,
    SimpleCameraThread, VideoSlotWidget,
)
from dialogs import DatePickerDialog

import cv2
import storage
import reports


# ─────────────────────────── PATIENT INFO FORM ───────────────────────────────
class MergedPatientForm(QWidget):
    def __init__(self):
        super().__init__()
        self._locked = False
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Action bar ──
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
        self._btn_edit_toggle.setVisible(False)
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

    def _set_locked(self, locked: bool):
        self._locked = locked
        ro_style = (
            "color: #ccc; background-color: #1e1e1e; "
            "border: 1px solid #3a3a3a; border-radius: 4px;"
        )
        edit_style = ""
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
        self._btn_edit_toggle.style().unpolish(self._btn_edit_toggle)
        self._btn_edit_toggle.style().polish(self._btn_edit_toggle)

    def _toggle_edit_mode(self):
        self._set_locked(not self._locked)

    def load_patient(self, data: dict):
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
        merged = {**existing, **data}
        try:
            with open(pat_json, "w") as fh:
                json.dump(merged, fh, indent=2)
        except Exception as e:
            print(f"Could not save to assets folder: {e}")


# ─────────────────────────── SETUP / VIDEO PAGE ───────────────────────────────
class SetupPage(QWidget):
    """Patient setup page: record MP4 videos, manage per-exercise thresholds, view thumbnails."""

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

        self._knee_samples: list[float] = []
        self._hip_samples: list[float] = []
        self._last_knee = 0.0
        self._last_hip = 0.0

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        # ─── LEFT PANEL ───
        left_panel = QWidget()
        left_panel.setMinimumWidth(220)
        left_panel.setMaximumWidth(320)

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

        # ─── CENTER PANEL ───
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setStyleSheet(
            "background-color: #2c3e50; color: #f39c12; font-size: 11px; "
            "border: 1px solid #f39c12; border-radius: 4px; padding: 4px 8px;"
        )
        self._banner.setVisible(False)
        center_layout.addWidget(self._banner)

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

        ex_row = QHBoxLayout()
        ex_row.addWidget(QLabel("Exercise:"))
        self.combo_exercise_setup = QComboBox()
        self.combo_exercise_setup.addItems([
            "Seated Knee Bending",
            "Straight Leg Raises",
            "Mini-squats",
        ])
        self.combo_exercise_setup.setMinimumWidth(220)
        ex_row.addWidget(self.combo_exercise_setup)
        ex_row.addStretch()
        center_layout.addLayout(ex_row)

        self.cam_frame = CameraDisplayWidget("Camera Offline")
        self.cam_frame.setMinimumHeight(320)
        self.cam_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_layout.addWidget(self.cam_frame, stretch=1)

        # Live angles bar
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

        # Recording controls
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
        self.lbl_rec_status.setStyleSheet("color: #e74c3c; font-weight: bold; border: none;")
        self.lbl_rec_status.setMinimumWidth(120)
        rec_row.addWidget(self.lbl_rec_status)
        center_layout.addLayout(rec_row)

        # ── Bottom controls ──
        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(6)

        thresh_grp = QGroupBox("Exercise Thresholds")
        tg = QGridLayout(thresh_grp)
        tg.setSpacing(6)
        tg.setContentsMargins(8, 6, 8, 8)

        self.spin_knee_flex_target = QSpinBox()
        self.spin_knee_flex_target.setRange(0, 180)
        self.spin_knee_flex_target.setSuffix("°")

        self.spin_knee_flex_max_allowed = QSpinBox()
        self.spin_knee_flex_max_allowed.setRange(0, 180)
        self.spin_knee_flex_max_allowed.setSuffix("°")

        self.spin_knee_flex_min = QSpinBox()
        self.spin_knee_flex_min.setRange(0, 180)
        self.spin_knee_flex_min.setSuffix("°")

        self.spin_knee_flex_max = QSpinBox()
        self.spin_knee_flex_max.setRange(0, 180)
        self.spin_knee_flex_max.setSuffix("°")

        tg.addWidget(QLabel("Target knee flexion:"), 0, 0)
        tg.addWidget(self.spin_knee_flex_target,     0, 1)
        tg.addWidget(QLabel("Max allowed (safety):"), 0, 2)
        tg.addWidget(self.spin_knee_flex_max_allowed, 0, 3)

        tg.addWidget(QLabel("Valid range min:"), 1, 0)
        tg.addWidget(self.spin_knee_flex_min,    1, 1)
        tg.addWidget(QLabel("Valid range max:"), 1, 2)
        tg.addWidget(self.spin_knee_flex_max,    1, 3)

        ctrl_layout.addWidget(thresh_grp)

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

        btn_save_setup = QPushButton("💾  Save Setup")
        btn_save_setup.setObjectName("Primary")
        btn_save_setup.setFixedHeight(34)
        btn_save_setup.clicked.connect(self._save_setup_full)
        ctrl_layout.addWidget(btn_save_setup)

        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidget(ctrl_widget)
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setMaximumHeight(160)
        ctrl_scroll.setFrameShape(QFrame.Shape.NoFrame)
        ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        center_layout.addWidget(ctrl_scroll)

        # ── Wiring ──
        self.combo_exercise_setup.currentTextChanged.connect(self._on_exercise_changed)

        self.spin_knee_flex_target.valueChanged.connect(lambda *_: self._persist_exercise_setup())
        self.spin_knee_flex_max_allowed.valueChanged.connect(lambda *_: self._persist_exercise_setup())
        self.spin_knee_flex_min.valueChanged.connect(lambda *_: self._persist_exercise_setup())
        self.spin_knee_flex_max.valueChanged.connect(lambda *_: self._persist_exercise_setup())

        self._on_exercise_changed(self.combo_exercise_setup.currentText())

        main_layout.addWidget(center_widget, stretch=1)

    def _refresh_model_marks(self):
        pid = self._get_pid()
        if not pid:
            return
        data = self._read_patient_json(pid)

        model_videos = data.get("model_videos", {})
        if not isinstance(model_videos, dict):
            model_videos = {}

        old_model_path = data.get("model_video", {}).get("path", "")

        for s in self.video_slots:
            ex_key = getattr(s, "exercise_key", canonical_exercise(s.name_lbl.text()))
            mv = model_videos.get(ex_key)
            model_path_for_ex = mv.get("path", "") if isinstance(mv, dict) else ""
            is_model = (s.video_path == model_path_for_ex) or (not model_path_for_ex and s.video_path == old_model_path)
            s.set_as_model(is_model)

    def _get_pid(self):
        info = PATIENT_DATA_STORE.get("merged_info", {})
        pid = str(info.get("id", "")).strip()
        if pid:
            return pid
        name = str(info.get("name", "")).strip()
        if name:
            return name.replace(" ", "_")
        return None

    def _has_real_id(self) -> bool:
        info = PATIENT_DATA_STORE.get("merged_info", {})
        return bool(str(info.get("id", "")).strip())

    def _read_patient_json(self, pid: str) -> dict:
        jp = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        if jp.exists():
            try:
                with open(jp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _write_patient_json(self, pid: str, data: dict) -> bool:
        jp = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        jp.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"_write_patient_json error: {e}")
            return False

    def _exercise_defaults(self) -> dict:
        return {
            "knee_flex_target": 60,
            "knee_flex_max_allowed": 120,
            "knee_flex_min": 10,
            "knee_flex_max": 160,
        }

    def _set_threshold_ui(self, vals: dict, block_signals: bool = True):
        widgets = [
            self.spin_knee_flex_target,
            self.spin_knee_flex_max_allowed,
            self.spin_knee_flex_min,
            self.spin_knee_flex_max,
        ]
        if block_signals:
            for w in widgets:
                w.blockSignals(True)

        self.spin_knee_flex_target.setValue(int(vals.get("knee_flex_target", 60)))
        self.spin_knee_flex_max_allowed.setValue(int(vals.get("knee_flex_max_allowed", 120)))
        self.spin_knee_flex_min.setValue(int(vals.get("knee_flex_min", 10)))
        self.spin_knee_flex_max.setValue(int(vals.get("knee_flex_max", 160)))

        if block_signals:
            for w in widgets:
                w.blockSignals(False)

    def _collect_threshold_ui(self) -> dict:
        return {
            "knee_flex_target": int(self.spin_knee_flex_target.value()),
            "knee_flex_max_allowed": int(self.spin_knee_flex_max_allowed.value()),
            "knee_flex_min": int(self.spin_knee_flex_min.value()),
            "knee_flex_max": int(self.spin_knee_flex_max.value()),
        }

    def _on_exercise_changed(self, exercise_name: str):
        pid = self._get_pid()
        if not pid:
            self._set_threshold_ui(self._exercise_defaults(), block_signals=True)
            return

        data = self._read_patient_json(pid)
        setup = data.get("setup", {})
        ex_map = setup.get("exercise_thresholds", {})

        vals = ex_map.get(exercise_name)
        if not isinstance(vals, dict):
            old = data.get("thresholds", {})
            if isinstance(old, dict) and old:
                vals = {
                    "knee_flex_target": old.get("knee_flex_target", 60),
                    "knee_flex_max_allowed": old.get("knee_flex_max_allowed", 120),
                    "knee_flex_min": old.get("knee_flex_min", 10),
                    "knee_flex_max": old.get("knee_flex_max", 160),
                }
            else:
                vals = self._exercise_defaults()

        self._set_threshold_ui(vals, block_signals=True)

    def _persist_exercise_setup(self):
        pid = self._get_pid()
        if not pid:
            return

        ex_name = self.combo_exercise_setup.currentText().strip()
        if not ex_name:
            return

        ex_key = canonical_exercise(ex_name)

        data = self._read_patient_json(pid)
        setup = data.get("setup")
        if not isinstance(setup, dict):
            setup = {}

        ex_map = setup.get("exercise_thresholds")
        if not isinstance(ex_map, dict):
            ex_map = {}

        ex_map[ex_key] = self._collect_threshold_ui()
        setup["exercise_thresholds"] = ex_map
        data["setup"] = setup

        self._write_patient_json(pid, data)

    def refresh_patient(self):
        info = PATIENT_DATA_STORE.get("merged_info", {})
        name = info.get("name", "")
        pid  = info.get("id", "")

        parts = []
        if name:
            parts.append(name)
        if pid:
            parts.append(f"ID: {pid}")
        self.lbl_patient.setText("\n".join(parts) if parts else "No patient selected")

        folder_pid = self._get_pid()
        if not folder_pid:
            self._banner.setText("⚠  No patient loaded. Fill in Patient Profile and save it first.")
            self._banner.setVisible(True)
        elif not self._has_real_id():
            self._banner.setText(
                f"⚠  No Patient ID set — data saved under '{folder_pid}'. "
                "Set an ID in Patient Profile for permanent records."
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        self._load_existing_videos(folder_pid)
        if folder_pid:
            self._load_setup_data(folder_pid)

        self._on_exercise_changed(self.combo_exercise_setup.currentText())

    def _load_existing_videos(self, pid):
        for slot in self.video_slots:
            slot.deleteLater()
        self.video_slots.clear()

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
            lbl.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;")
            self.video_layout.insertWidget(0, lbl)
            return

        json_path = Path(PATIENT_ASSETS_FOLDER) / pid / "patient.json"
        model_path = ""
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                model_videos = data.get("model_videos", {})
                if not isinstance(model_videos, dict):
                    model_videos = {}

                old_model_path = data.get("model_video", {}).get("path", "")

                videos_list = data.get("setup", {}).get("videos") or data.get("videos", [])
                for i, v in enumerate(videos_list):
                    vpath = v.get("path", "")
                    tpath = v.get("thumb", "")
                    label = v.get("exercise", f"Video {i+1}")
                    if vpath and Path(vpath).exists():
                        slot = VideoSlotWidget(i + 1, vpath,
                                               tpath if tpath and Path(tpath).exists() else None,
                                               label)
                        ex_key = v.get("exercise_key") or canonical_exercise(label)
                        slot.exercise_key = ex_key

                        model_path_for_ex = ""
                        mv = model_videos.get(ex_key)
                        if isinstance(mv, dict):
                            model_path_for_ex = mv.get("path", "")

                        is_model = (str(vpath) == str(model_path_for_ex)) or (not model_path_for_ex and str(vpath) == str(old_model_path))
                        slot.set_as_model(is_model)
                        slot._angle_meta = v.get("angles", {})
                        slot._created_at = v.get("created_at", "")
                        slot._notes = v.get("notes", "")
                        slot.deleted.connect(self._remove_video_slot)
                        slot.model_selected.connect(self._on_model_selected)
                        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
                        self.video_slots.append(slot)
            except Exception as e:
                print(f"_load_existing_videos error: {e}")

        if not self.video_slots:
            lbl = QLabel("No setup videos yet.\nUse ⏺ START RECORDING to add one.")
            lbl.setObjectName("NoVideosPlaceholder")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;")
            self.video_layout.insertWidget(0, lbl)

    def _remove_video_slot(self, slot: "VideoSlotWidget"):
        if slot in self.video_slots:
            self.video_slots.remove(slot)
        slot.deleteLater()
        self._persist_video_metadata()

    def _persist_video_metadata(self):
        pid = self._get_pid()
        if not pid:
            return

        data = self._read_patient_json(pid)

        videos_payload = [
            {
                "path": str(s.video_path),
                "thumb": str(s.thumb_path) if s.thumb_path else "",
                "exercise": s.name_lbl.text(),
                "exercise_key": getattr(s, "exercise_key", canonical_exercise(s.name_lbl.text())),
                "angles": getattr(s, "_angle_meta", {}),
                "created_at": getattr(s, "_created_at", ""),
                "notes": getattr(s, "_notes", ""),
            }
            for s in self.video_slots if s.video_path
        ]

        setup = data.get("setup")
        if not isinstance(setup, dict):
            setup = {}
        setup["videos"] = videos_payload
        data["setup"] = setup
        data["videos"] = videos_payload

        self._write_patient_json(pid, data)

    def _save_setup_full(self):
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(self, "No Patient",
                                "No patient loaded. Please fill in Patient Profile first.")
            return

        data = self._read_patient_json(pid)

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

        setup = data.get("setup")
        if not isinstance(setup, dict):
            setup = {}

        setup["videos"] = videos_payload
        setup["angle_targets"] = angle_targets

        ex_map = setup.get("exercise_thresholds")
        if not isinstance(ex_map, dict):
            ex_map = {}
        ex_map[self.combo_exercise_setup.currentText().strip()] = self._collect_threshold_ui()
        setup["exercise_thresholds"] = ex_map

        data["setup"] = setup
        data["videos"] = videos_payload

        ok = self._write_patient_json(pid, data)
        if ok:
            QMessageBox.information(self, "Saved", "Setup saved to patient record.")
        else:
            QMessageBox.warning(self, "Error", "Could not save setup. Check console.")

    def _load_setup_data(self, pid: str):
        data = self._read_patient_json(pid)
        setup = data.get("setup", {})

        at = setup.get("angle_targets", {})
        for key, inp in self.angle_inputs.items():
            inp.setText(str(at.get(key, 0)))

    def _add_video_from_file(self):
        pid = self._get_pid()
        if not pid:
            QMessageBox.warning(self, "No Patient",
                                "No patient loaded. Please fill in Patient Profile first.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if not path:
            return

        label = self.combo_exercise_label.currentText()
        slot = VideoSlotWidget(len(self.video_slots) + 1, path, None, label)
        slot.exercise_key = canonical_exercise(label)
        slot._angle_meta = {}
        slot._created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        slot._notes = ""
        slot.deleted.connect(self._remove_video_slot)
        slot.model_selected.connect(self._on_model_selected)
        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
        self.video_slots.append(slot)

        for i in range(self.video_layout.count() - 1, -1, -1):
            item = self.video_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QLabel) and w.objectName() == "NoVideosPlaceholder":
                self.video_layout.removeWidget(w)
                w.deleteLater()

        self._persist_video_metadata()

    def _on_model_selected(self, slot: "VideoSlotWidget"):
        self._save_model_video(slot)
        self._refresh_model_marks()

    def _save_model_video(self, slot: "VideoSlotWidget"):
        pid = self._get_pid()
        if not pid:
            return

        data = self._read_patient_json(pid)

        model_videos = data.get("model_videos", {})
        if not isinstance(model_videos, dict):
            model_videos = {}

        ex_key = getattr(slot, "exercise_key", "") or canonical_exercise(slot.name_lbl.text())
        model_videos[ex_key] = {
            "path": str(slot.video_path),
            "thumb": str(slot.thumb_path) if slot.thumb_path else "",
            "exercise": slot.name_lbl.text(),
            "exercise_key": ex_key,
        }

        data["model_videos"] = model_videos
        data["model_video"] = model_videos[ex_key]

        ok = self._write_patient_json(pid, data)
        if ok:
            QMessageBox.information(
                self, "Model Set",
                f"★ Model video set for: {slot.name_lbl.text()}\n"
                f"(Exercise Key: {ex_key})"
            )

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
                "No patient loaded. Please fill in Patient Profile and save it first."
            )
            return

        vid_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "videos"
        thumb_dir = Path(PATIENT_ASSETS_FOLDER) / pid / "thumbs"
        vid_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        exercise_label = self.combo_exercise_label.currentText()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = exercise_label.replace(" ", "_").replace("/", "_")
        filename = f"{safe_label}_{timestamp}.avi"
        video_path = vid_dir / filename

        h, w = self.current_frame_bgr.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
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

        if self.current_frame_bgr is not None and self._thumb_path:
            try:
                thumb = cv2.resize(self.current_frame_bgr, (160, 100))
                cv2.imwrite(self._thumb_path, thumb)
            except Exception as e:
                print(f"Thumbnail error: {e}")
                self._thumb_path = None

        if self._recording_path and Path(self._recording_path).exists():
            label = self.combo_exercise_label.currentText()
            angle_meta = {}
            if self._knee_samples:
                angle_meta = {
                    "knee_min": round(min(self._knee_samples), 1),
                    "knee_max": round(max(self._knee_samples), 1),
                    "hip_min":  round(min(self._hip_samples), 1) if self._hip_samples else 0,
                    "hip_max":  round(max(self._hip_samples), 1) if self._hip_samples else 0,
                }
            self._add_video_slot(self._recording_path, self._thumb_path, label, angle_meta=angle_meta)
            self._persist_video_metadata()

        self._knee_samples.clear()
        self._hip_samples.clear()
        self._recording_path = None
        self._thumb_path = None

    def _add_video_slot(self, video_path: str, thumb_path: str | None, label: str,
                        angle_meta: dict | None = None):
        idx = len(self.video_slots) + 1
        slot = VideoSlotWidget(idx, video_path, thumb_path, label)
        slot.exercise_key = canonical_exercise(label)
        slot._angle_meta = angle_meta or {}
        slot.deleted.connect(self._remove_video_slot)
        slot.model_selected.connect(self._on_model_selected)
        self.video_layout.insertWidget(self.video_layout.count() - 1, slot)
        self.video_slots.append(slot)

    def stop_recording_if_needed(self):
        if self.recording:
            self._stop_recording()

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
        self._persist_video_metadata()
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


# ─────────────────────────── PATIENT HISTORY PAGE ────────────────────────────
class PatientHistoryPage(QWidget):
    """Session history + recorded videos for a loaded patient."""

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(8)

        self._lbl_name = QLabel("— no patient loaded —")
        self._lbl_name.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 15px; "
            "font-weight: bold; border: none;"
        )
        root.addWidget(self._lbl_name)

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
        while self._video_layout.count():
            w = self._video_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        pid = data.get("id", "").strip()
        name = data.get("name", "").replace(" ", "_")
        folder_id = pid if pid else name
        pat_json = Path(PATIENT_ASSETS_FOLDER) / folder_id / "patient.json"

        videos = list(data.get("videos", []))
        old_model_path = data.get("model_video", {}).get("path", "")
        model_videos = data.get("model_videos", {})
        if not isinstance(model_videos, dict):
            model_videos = {}
        if pat_json.exists():
            try:
                with open(pat_json) as f:
                    pj = json.load(f)
                if not videos:
                    videos = pj.get("videos", [])
                if not old_model_path:
                    old_model_path = pj.get("model_video", {}).get("path", "")

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

            ex_key = v.get("exercise_key") or canonical_exercise(exercise)
            mv = model_videos.get(ex_key)
            per_ex_model_path = mv.get("path", "") if isinstance(mv, dict) else ""

            is_model = bool(
                vid_path and (
                    vid_path == per_ex_model_path
                    or (not per_ex_model_path and vid_path == old_model_path)
                )
            )

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

        toolbar = QHBoxLayout()
        btn_upload = QPushButton("Upload Document")
        btn_upload.setObjectName("Primary")
        btn_upload.setFixedHeight(34)
        btn_upload.clicked.connect(self._upload)
        toolbar.addWidget(btn_upload)
        toolbar.addStretch()
        root.addLayout(toolbar)

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

        monthly_grp = QGroupBox("Monthly Report")
        ml = QVBoxLayout(monthly_grp)
        ml.setSpacing(8)

        ml.addWidget(QLabel("Generate a PDF summary for a specific month:"))

        self._selected_date = QDate.currentDate()
        m_controls = QHBoxLayout()
        m_controls.addWidget(QLabel("Report period:"))
        self._btn_date_pick = QPushButton(
            self._selected_date.toString("MMMM yyyy")
        )
        self._btn_date_pick.setMinimumWidth(180)
        self._btn_date_pick.setFixedHeight(34)
        self._btn_date_pick.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; "
            "border: 1px solid #2ecc71; border-radius: 4px; "
            "color: #2ecc71; font-weight: bold; padding: 0 12px; text-align: left;"
        )
        self._btn_date_pick.clicked.connect(self._open_date_picker)
        m_controls.addWidget(self._btn_date_pick)
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

    def _open_date_picker(self):
        dlg = DatePickerDialog(self._selected_date, self)
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._selected_date = dlg.selected_date()
            self._btn_date_pick.setText(self._selected_date.toString("MMMM yyyy"))

    def _gen_monthly(self):
        if not self._patient_data:
            QMessageBox.warning(self, "No Patient", "Load a patient first.")
            return
        sessions = storage.load_sessions(self._patient_data)
        year  = self._selected_date.year()
        month = self._selected_date.month()
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
    """Hospital-style read-only patient summary."""

    def __init__(self):
        super().__init__()
        self._patient_data: dict = {}
        self._sessions: list = []
        self._navigate_to = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(6)

        toolbar = QHBoxLayout()
        title_lbl = QLabel("PATIENT FILE")
        title_lbl.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 18px; "
            "font-weight: bold; border: none;"
        )
        toolbar.addWidget(title_lbl)
        toolbar.addStretch()

        _btn_style = (
            "font-size: 11px; padding: 4px 10px; border-radius: 4px; "
            f"background-color: {ModernTheme.BG_LIGHT}; "
            "border: 1px solid #555; color: #ccc;"
        )
        btn_edit_info = QPushButton("✎  Edit Profile")
        btn_edit_info.setFixedHeight(28)
        btn_edit_info.setStyleSheet(_btn_style)
        btn_edit_info.setToolTip("Go to Patient Profile and edit information")
        btn_edit_info.clicked.connect(lambda: self._nav(0))
        toolbar.addWidget(btn_edit_info)

        btn_setup = QPushButton("⚙  Setup & Targets")
        btn_setup.setFixedHeight(28)
        btn_setup.setStyleSheet(_btn_style)
        btn_setup.setToolTip("Edit exercise setup, angle targets and recorded videos")
        btn_setup.clicked.connect(lambda: self._nav(1))
        toolbar.addWidget(btn_setup)

        btn_progress = QPushButton("📈  View Progress")
        btn_progress.setFixedHeight(28)
        btn_progress.setStyleSheet(_btn_style)
        btn_progress.setToolTip("View session history and patient improvement")
        btn_progress.clicked.connect(lambda: self._nav(4))
        toolbar.addWidget(btn_progress)

        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {ModernTheme.ACCENT_PRIMARY};")
        sep.setFixedHeight(2)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")
        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        cl = QVBoxLayout(content)
        cl.setSpacing(12)

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

    def _nav(self, page_index: int):
        if callable(self._navigate_to):
            self._navigate_to(page_index)

    def refresh_patient(self, patient_data: dict):
        self._patient_data = patient_data
        pj = storage.load_patient_json(patient_data)
        merged = {**patient_data, **pj}
        sessions = storage.load_sessions(patient_data)
        self._sessions = sessions
        self._populate(merged, sessions)

    def _populate(self, data: dict, sessions: list):
        for key, lbl in self._id_labels.items():
            lbl.setText(str(data.get(key, "") or "—"))

        for key, lbl in self._notes_labels.items():
            lbl.setText(str(data.get(key, "") or "—"))

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

        docs = data.get("documents", [])
        if docs:
            lines = [f"• {d.get('title','—')}  ({d.get('filename','—')})  — {d.get('date_added','')}"
                     for d in docs]
            self._docs_list.setText("\n".join(lines))
        else:
            self._docs_list.setText("No documents on file.")

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
