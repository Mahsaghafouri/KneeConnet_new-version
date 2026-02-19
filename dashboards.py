import json
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QSizePolicy, QInputDialog, QDialog,
    QComboBox, QLineEdit, QMessageBox, QStackedWidget, QListWidget, QGridLayout,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from vision_thread import CameraThread as VisionCameraThread
from voice_thread import TTSWorker

from theme import ModernTheme
import constants
from constants import (
    PATIENT_ASSETS_FOLDER, PATIENT_DATA_STORE,
    canonical_exercise, SessionManager, create_app_icon,
)
from widgets import HeaderLabel, SubHeaderLabel
from dialogs import ProgressDialog
from pages import (
    MergedPatientForm, SetupPage, ExerciseForm,
    PatientHistoryPage, DocumentsPage, ReportsPage, PatientFilePage,
)


# ─────────────────────────── PATIENT DASHBOARD ───────────────────────────────
class PatientDashboard(QDialog):
    PAGE_INFO      = 0
    PAGE_SETUP     = 1
    PAGE_EXERCISE  = 2
    PAGE_DOCUMENTS = 3
    PAGE_HISTORY   = 4
    PAGE_FILE      = 5
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

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-right: 1px solid #444;"
        )
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(260)

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

        # ── Content area ──
        content_area = QFrame()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.stack = QStackedWidget()

        self.form = MergedPatientForm()
        self.stack.addWidget(self.form)

        self.setup_page = SetupPage()
        self.stack.addWidget(self.setup_page)

        self.stack.addWidget(ExerciseForm())

        self.documents_page = DocumentsPage()
        self.stack.addWidget(self.documents_page)

        self.history_page = PatientHistoryPage()
        self.stack.addWidget(self.history_page)

        self.patient_file_page = PatientFilePage()
        self.patient_file_page._navigate_to = self.list_widget.setCurrentRow
        self.stack.addWidget(self.patient_file_page)

        self.reports_page = ReportsPage()
        self.stack.addWidget(self.reports_page)

        content_layout.addWidget(self.stack)
        main_layout.addWidget(content_area)

    def display_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == self.PAGE_SETUP:
            self.setup_page.start_camera()
            self.setup_page.refresh_patient()
        else:
            self.setup_page.stop_camera()
        data = PATIENT_DATA_STORE.get("merged_info", {})
        if index == self.PAGE_DOCUMENTS:
            self.documents_page.refresh_patient(data)
        elif index == self.PAGE_FILE:
            self.patient_file_page.refresh_patient(data)
        elif index == self.PAGE_REPORTS:
            self.reports_page.refresh_patient(data)

    def _load_patient(self, data: dict):
        PATIENT_DATA_STORE["merged_info"] = data
        name = data.get("name", "").strip()
        pid  = data.get("id", "").strip()
        label = name if name else pid if pid else "Unknown"
        self.setWindowTitle(f"Patient Dashboard — {label}")

        self.form.load_patient(data)
        self.history_page.load_patient(data)
        self.documents_page.refresh_patient(data)
        self.patient_file_page.refresh_patient(data)
        self.reports_page.refresh_patient(data)
        self.setup_page.refresh_patient()
        self.list_widget.setCurrentRow(self.PAGE_FILE)

    def closeEvent(self, event):
        self.setup_page.stop_camera()
        super().closeEvent(event)


# ─────────────────────────── MAIN WINDOW ─────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KneeConnect - Professional Edition")
        self.setWindowIcon(create_app_icon())
        self.resize(1200, 750)

        self.thread_cam: VisionCameraThread | None = None
        self.is_running = False
        self.camera_on = True
        self._loop_video = True

        self.tts_worker = TTSWorker(cooldown_seconds=4.0)
        self.tts_worker.start()

        self.session_start_time: float | None = None
        self.session_correct_reps = 0
        self.session_total_reps = 0
        self.session_min_knee = float("inf")
        self.session_max_knee = 0.0
        self.session_exercise = ""

        self.session_left_correct = 0
        self.session_left_total = 0
        self.session_right_correct = 0
        self.session_right_total = 0

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

        _info = PATIENT_DATA_STORE.get("merged_info", {})
        _name = _info.get("name", "").strip()
        _pid = _info.get("id", "").strip()
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
        cam_card = QFrame()
        cam_card.setObjectName("Card")
        cam_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        cam_card_layout = QVBoxLayout(cam_card)
        cam_card_layout.setContentsMargins(8, 8, 8, 8)
        cam_card_layout.setSpacing(6)

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
        self.feed_label.setMinimumSize(480, 320)
        cam_card_layout.addWidget(self.feed_label, stretch=1)

        instr_card = QFrame()
        instr_card.setObjectName("Card")
        instr_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        instr_layout = QVBoxLayout(instr_card)
        instr_layout.setContentsMargins(8, 8, 8, 8)
        instr_layout.setSpacing(6)

        instr_title = QLabel("Instructional Video")
        instr_title.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 12px; border: none;"
        )
        instr_layout.addWidget(instr_title)

        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        instr_layout.addWidget(self.video_widget, stretch=1)

        self.audio_output = QAudioOutput(self)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.errorOccurred.connect(self._on_media_error)
        self.media_player.mediaStatusChanged.connect(self._on_media_status)

        from PyQt6.QtWidgets import QSplitter
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(cam_card)
        split.addWidget(instr_card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([800, 500])

        root.addWidget(split, stretch=1)

        # ── Stats bar ──
        stats = QFrame()
        stats.setObjectName("Card")
        stats_l = QHBoxLayout(stats)
        stats_l.setContentsMargins(12, 8, 12, 8)
        stats_l.setSpacing(18)

        def make_stat(title: str) -> QLabel:
            w = QWidget()
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(2)

            t = QLabel(title)
            t.setStyleSheet("color: #bdc3c7; font-size: 11px; border: none;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)

            v = QLabel("—")
            v.setStyleSheet("color: #1abc9c; font-size: 16px; font-weight: bold; border: none;")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)

            l.addWidget(t)
            l.addWidget(v)
            stats_l.addWidget(w)
            return v

        self.lbl_reps = make_stat("Reps (correct/total)")
        self.lbl_knee_angle = make_stat("Knee Angle (°)")
        self.lbl_hip_angle = make_stat("Hip Angle (°)")

        self._left_col_widget = QWidget()
        left_l = QVBoxLayout(self._left_col_widget)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(2)
        left_t = QLabel("Left Leg (correct/total)")
        left_t.setStyleSheet("color: #bdc3c7; font-size: 11px; border: none;")
        self.lbl_left_reps = QLabel("—")
        self.lbl_left_reps.setStyleSheet("color: #1abc9c; font-size: 16px; font-weight: bold; border: none;")
        left_l.addWidget(left_t, alignment=Qt.AlignmentFlag.AlignCenter)
        left_l.addWidget(self.lbl_left_reps, alignment=Qt.AlignmentFlag.AlignCenter)
        stats_l.addWidget(self._left_col_widget)

        self._right_col_widget = QWidget()
        right_l = QVBoxLayout(self._right_col_widget)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(2)
        right_t = QLabel("Right Leg (correct/total)")
        right_t.setStyleSheet("color: #bdc3c7; font-size: 11px; border: none;")
        self.lbl_right_reps = QLabel("—")
        self.lbl_right_reps.setStyleSheet("color: #1abc9c; font-size: 16px; font-weight: bold; border: none;")
        right_l.addWidget(right_t, alignment=Qt.AlignmentFlag.AlignCenter)
        right_l.addWidget(self.lbl_right_reps, alignment=Qt.AlignmentFlag.AlignCenter)
        stats_l.addWidget(self._right_col_widget)

        self._left_col_widget.setVisible(False)
        self._right_col_widget.setVisible(False)

        root.addWidget(stats)

        # ── Control bar ──
        control_bar = QFrame()
        control_bar.setObjectName("Card")
        control_bar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-radius: 40px;"
        )
        control_bar.setMinimumHeight(70)
        control_bar.setMaximumHeight(90)

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

        _prog_label = "Reports" if constants.CURRENT_USER_ROLE == "admin" else "Progress"
        self.btn_show_progress = QPushButton(_prog_label)
        self.btn_show_progress.setFixedWidth(110)
        if constants.CURRENT_USER_ROLE == "admin":
            self.btn_show_progress.setObjectName("Primary")
        ctrl.addWidget(self.btn_show_progress)

        admin_btn_label = "Patient Dashboard" if constants.CURRENT_USER_ROLE == "admin" else "My Profile"
        self.btn_patient_admin = QPushButton(admin_btn_label)
        self.btn_patient_admin.setFixedWidth(150)
        if constants.CURRENT_USER_ROLE == "admin":
            self.btn_patient_admin.setObjectName("Primary")
        ctrl.addWidget(self.btn_patient_admin)

        root.addWidget(control_bar)

        # ── Signals ──
        self.btn_exercise.clicked.connect(self.select_exercise)
        self.btn_start.clicked.connect(self.toggle_start)
        self.btn_stop.clicked.connect(self.stop_process)
        self.btn_show_progress.clicked.connect(self.show_progress)
        self.btn_patient_admin.clicked.connect(self.open_patient_admin)

        self.start_camera_thread()

    # ── Camera thread management ──
    def start_camera_thread(self):
        if self.thread_cam is None:
            try:
                self.thread_cam = VisionCameraThread()
                self.thread_cam.use_webcam = True
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
            time.sleep(0.5)
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

    # ── Exercise selection & video playback ──
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
        self._loop_video = True

        if self.thread_cam is None and self.camera_on:
            self.start_camera_thread()

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

            ex_key = canonical_exercise(exercise)

            model_videos = data.get("model_videos", {})
            if isinstance(model_videos, dict):
                mv = model_videos.get(ex_key)
                if isinstance(mv, dict):
                    vpath = mv.get("path", "")
                    if vpath and Path(vpath).exists():
                        return vpath

            model = data.get("model_video", {})
            if isinstance(model, dict):
                vpath = model.get("path", "")
                if vpath and Path(vpath).exists():
                    model_ex = model.get("exercise", "")
                    if canonical_exercise(model_ex) == ex_key:
                        return vpath
        except Exception:
            pass
        return None

    def _on_media_error(self, error, error_string):
        print("Media player error:", error, error_string)

    @pyqtSlot(QMediaPlayer.MediaStatus)
    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._loop_video and self.is_running:
                self.media_player.setPosition(0)
                self.media_player.play()

    # ── Processing controls ──
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
                self.is_running = True
                self.btn_start.setText("PAUSE")
                self.lbl_status.setText("Tracking Active")
                if self.thread_cam is not None:
                    self.thread_cam.countdown_state = "idle"
                    self.thread_cam.process_enabled = True
            else:
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
        self._loop_video = False
        self.btn_start.setText("START")
        self.lbl_status.setText("Session Stopped")
        if self.thread_cam is not None:
            self.thread_cam.process_enabled = False
            self.thread_cam.countdown_state = "idle"

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
            if self.session_exercise == "Straight Leg Raises":
                session_data["left_correct_reps"] = self.session_left_correct
                session_data["left_total_reps"] = self.session_left_total
                session_data["right_correct_reps"] = self.session_right_correct
                session_data["right_total_reps"] = self.session_right_total
            SessionManager.save(session_data)

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

    # ── Patient Dashboard / My Profile ──
    def open_patient_admin(self):
        if constants.CURRENT_USER_ROLE == "admin":
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

            if self.camera_on:
                self.start_camera_thread()
                if self.is_running and self.thread_cam is not None:
                    self.thread_cam.process_enabled = True
        else:
            dlg = PatientDashboardLite(self)
            dlg.exec()

    def show_progress(self):
        if constants.CURRENT_USER_ROLE == "admin":
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

    # ── Stats update ──
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
    def update_side_reps(self, left_correct: int, left_total: int, right_correct: int, right_total: int):
        self.session_left_correct = left_correct
        self.session_left_total = left_total
        self.session_right_correct = right_correct
        self.session_right_total = right_total
        self.lbl_left_reps.setText(f"{left_correct}/{left_total}")
        self.lbl_right_reps.setText(f"{right_correct}/{right_total}")

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
    """Doctor's first screen: searchable list of all patients."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KneeConnect — Patient Browser (Admin)")
        self.setWindowIcon(create_app_icon())
        self.resize(760, 560)

        self._all_patients: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        hdr_row = QHBoxLayout()
        hdr_row.addWidget(HeaderLabel("PATIENT BROWSER"))
        hdr_row.addStretch()
        btn_new = QPushButton("+ New Patient")
        btn_new.setObjectName("Primary")
        btn_new.setFixedSize(140, 36)
        btn_new.clicked.connect(self._create_new_patient)
        hdr_row.addWidget(btn_new)
        root.addLayout(hdr_row)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search by name, ID, surgeon or physio…")
        self._search.textChanged.connect(self._filter)
        root.addWidget(self._search)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet(
            "QListWidget { alternate-background-color: #333; } "
            "QListWidget::item { padding: 10px; border-radius: 4px; } "
        )
        self._list.itemDoubleClicked.connect(self._open_selected)
        self._list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self._list, stretch=1)

        self._lbl_detail = QLabel("")
        self._lbl_detail.setStyleSheet(
            f"color: {ModernTheme.TEXT_GRAY}; font-size: 11px; border: none;"
        )
        root.addWidget(self._lbl_detail)

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
        dashboard._load_patient(data)
        dashboard.exec()

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

        wrapper = QHBoxLayout()
        wrapper.setSpacing(0)

        sidebar = QFrame()
        sidebar.setStyleSheet(
            f"background-color: {ModernTheme.BG_LIGHT}; border-right: 1px solid #444;"
        )
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(260)

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

        content = QFrame()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)

        self._stack = QStackedWidget()

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
