import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSizePolicy, QLineEdit, QTextEdit, QComboBox, QFormLayout,
    QScrollArea, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QPen

import numpy as np
import cv2

from theme import ModernTheme
from constants import PATIENT_DATA_STORE, canonical_exercise
from utils import calculate_angle, get_visible_side


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


# ─────────────────────────── VIDEO SLOT WIDGET ────────────────────────────────
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
        self.exercise_key = canonical_exercise(label) if label else ""
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
