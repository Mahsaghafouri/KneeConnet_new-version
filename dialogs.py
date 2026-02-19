import json
from datetime import date
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QCheckBox, QTextEdit, QLineEdit, QInputDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QCalendarWidget, QGridLayout, QListWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QPixmap

from theme import ModernTheme
from constants import (
    PATIENT_ASSETS_FOLDER, PATIENT_DATA_STORE,
    create_app_icon,
)
from widgets import HeaderLabel, SubHeaderLabel
import storage


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


# ─────────────────────────── DATE PICKER DIALOG ──────────────────────────────
class DatePickerDialog(QDialog):
    """Full calendar date picker — day / month / year with navigation."""

    def __init__(self, initial_date: QDate | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Report Date")
        self.setWindowIcon(create_app_icon())
        self.setFixedWidth(340)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── Calendar widget ───────────────────────────────────────────────────
        self._cal = QCalendarWidget()
        self._cal.setGridVisible(True)
        self._cal.setNavigationBarVisible(True)
        if initial_date and initial_date.isValid():
            self._cal.setSelectedDate(initial_date)
        else:
            self._cal.setSelectedDate(QDate.currentDate())

        # Dark-theme stylesheet for the calendar
        self._cal.setStyleSheet("""
            QCalendarWidget QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                alternate-background-color: #2a2a2a;
            }
            QCalendarWidget QAbstractItemView {
                background-color: #1e1e1e;
                color: #ffffff;
                selection-background-color: #2ecc71;
                selection-color: #000000;
                border: none;
            }
            QCalendarWidget QAbstractItemView:disabled {
                color: #555555;
            }
            QCalendarWidget QToolButton {
                background-color: #2c3e50;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QCalendarWidget QToolButton:hover {
                background-color: #3d5166;
            }
            QCalendarWidget QMenu {
                background-color: #2c3e50;
                color: #ffffff;
                border: 1px solid #555;
            }
            QCalendarWidget QSpinBox {
                background-color: #2c3e50;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
            }
            QCalendarWidget #qt_calendar_navigationbar {
                background-color: #2c3e50;
                padding: 4px;
                border-bottom: 1px solid #444;
            }
            QCalendarWidget #qt_calendar_prevmonth,
            QCalendarWidget #qt_calendar_nextmonth {
                qproperty-icon: none;
                color: #2ecc71;
                font-size: 16px;
                font-weight: bold;
                border: none;
                padding: 2px 6px;
            }
        """)

        # Double-click on a day immediately accepts
        self._cal.activated.connect(lambda _d: self.accept())
        root.addWidget(self._cal)

        # ── Selected date preview ─────────────────────────────────────────────
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            f"color: {ModernTheme.ACCENT_PRIMARY}; font-size: 13px; "
            "font-weight: bold; border: none; padding: 4px;"
        )
        self._cal.selectionChanged.connect(self._update_preview)
        self._update_preview()
        root.addWidget(self._preview)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✔  Use This Date")
        btn_ok.setObjectName("Primary")
        btn_ok.setFixedHeight(34)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def _update_preview(self):
        d = self._cal.selectedDate()
        self._preview.setText(d.toString("dddd, d MMMM yyyy"))

    def selected_date(self) -> QDate:
        return self._cal.selectedDate()


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
        self._shown_patients = patients
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


# ─────────────────────────── PROGRESS DIALOG ─────────────────────────────────
class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Progress Report")
        self.setWindowIcon(create_app_icon())
        self.resize(900, 600)

        from datetime import datetime
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
        lbl_pi = QLabel("\U0001f9d1\u200d\U0001f9bd")
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
        lbl_di = QLabel("\U0001f468\u200d\u2695\ufe0f")
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
