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
