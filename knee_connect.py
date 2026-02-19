import sys

from PyQt6.QtWidgets import QApplication, QDialog

from theme import ModernTheme
from constants import PATIENT_DATA_STORE, create_app_icon
import constants
from dialogs import TermsDialog, RoleSelectionDialog, PatientLoginDialog
from dashboards import MainWindow, AdminPatientBrowser


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(ModernTheme.STYLESHEET)
    app.setWindowIcon(create_app_icon())

    # ── Step 1: Terms of Service ──
    terms = TermsDialog()
    terms.show()
    terms.raise_()
    terms.activateWindow()
    if terms.exec() != QDialog.DialogCode.Accepted:
        sys.exit()

    # ── Step 2: Role selection ──
    role_dlg = RoleSelectionDialog()
    role_dlg.show()
    role_dlg.raise_()
    role_dlg.activateWindow()
    if role_dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit()

    role = role_dlg.chosen_role()

    # ── Doctor / Physiotherapist path ──
    if role == RoleSelectionDialog.DOCTOR:
        constants.CURRENT_USER_ROLE = "admin"
        browser = AdminPatientBrowser()
        browser.show()
        browser.raise_()
        browser.activateWindow()
        sys.exit(app.exec())

    # ── Patient path ──
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
