"""
reports.py — KneeConnect PDF report generator.

Tries to use reportlab; if not installed, falls back to writing a
plain-text .txt report (still opens automatically).

Public API:
    generate_monthly_report(patient_data, sessions, year, month) -> Path | None
    generate_full_record(patient_data, sessions)                  -> Path | None
"""

import os
from datetime import datetime
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from storage import get_reports_folder, ensure_patient_folder


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _open_file(path: Path):
    """Open the file with the default OS viewer."""
    try:
        os.startfile(str(path.resolve()))
    except Exception as e:
        print(f"Could not open report: {e}")


def _secs_to_str(secs: float) -> str:
    secs = int(secs)
    return f"{secs // 3600:02d}h {(secs % 3600) // 60:02d}m {secs % 60:02d}s"


def _patient_header_lines(patient_data: dict) -> list[str]:
    d = patient_data
    lines = [
        f"Patient: {d.get('name', '—')}",
        f"ID: {d.get('id', '—')}   |   Age: {d.get('age', '—')}   |   Gender: {d.get('gender', '—')}",
        f"Surgeon: {d.get('surgeon', '—')}   |   Physiotherapist: {d.get('physio', '—')}",
        f"Surgery date: {d.get('surgery_date', '—')}",
    ]
    return lines


# ─── Monthly Report ──────────────────────────────────────────────────────────

def generate_monthly_report(patient_data: dict, sessions: list,
                             year: int | None = None,
                             month: int | None = None) -> Path | None:
    """
    Generate a monthly summary PDF (or .txt) for one patient.
    Returns the output Path on success, or None on failure.
    """
    now = datetime.now()
    year  = year  or now.year
    month = month or now.month
    month_prefix = f"{year}-{month:02d}"

    month_sessions = [s for s in sessions if s.get("date", "").startswith(month_prefix)]

    folder = get_reports_folder(patient_data)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"monthly_report_{month_prefix}.pdf" if HAS_REPORTLAB else f"monthly_report_{month_prefix}.txt"
    output_path = folder / filename

    if HAS_REPORTLAB:
        return _monthly_pdf(patient_data, month_sessions, year, month, output_path)
    else:
        return _monthly_txt(patient_data, month_sessions, year, month, output_path)


def _monthly_pdf(patient_data, sessions, year, month, out: Path) -> Path | None:
    try:
        doc = SimpleDocTemplate(str(out), pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style   = ParagraphStyle("Title2", parent=styles["Title"],   fontSize=18, spaceAfter=4)
        header_style  = ParagraphStyle("Header2", parent=styles["Heading2"], fontSize=12, spaceAfter=4)
        normal_style  = styles["Normal"]
        normal_style.fontSize = 10

        import calendar
        month_name = calendar.month_name[month]

        story = []
        story.append(Paragraph("KneeConnect — Monthly Report", title_style))
        story.append(Paragraph(f"{month_name} {year}", header_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3*cm))

        for line in _patient_header_lines(patient_data):
            story.append(Paragraph(line, normal_style))
        story.append(Spacer(1, 0.4*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Spacer(1, 0.3*cm))

        # Summary
        total = len(sessions)
        correct = sum(s.get("correct_reps", 0) for s in sessions)
        secs   = sum(s.get("duration_seconds", 0) for s in sessions)
        best   = max((s.get("max_knee_angle", 0) for s in sessions), default=0)
        story.append(Paragraph("Monthly Summary", header_style))
        summary_data = [
            ["Total Sessions", "Total Correct Reps", "Total Time", "Best Angle (°)"],
            [str(total), str(correct), _secs_to_str(secs), f"{best:.1f}"],
        ]
        summary_table = Table(summary_data, hAlign="LEFT")
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1abc9c")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 0.5*cm))

        # Session table
        story.append(Paragraph("Sessions This Month", header_style))
        headers = ["Date", "Exercise", "Duration", "Correct Reps", "Total Reps", "Min°", "Max°"]
        rows = [headers]
        for s in sessions:
            dur_str = _secs_to_str(s.get("duration_seconds", 0))
            rows.append([
                s.get("date", ""),
                s.get("exercise", ""),
                dur_str,
                str(s.get("correct_reps", 0)),
                str(s.get("total_reps", 0)),
                f"{s.get('min_knee_angle', 0):.1f}",
                f"{s.get('max_knee_angle', 0):.1f}",
            ])
        if len(rows) == 1:
            rows.append(["No sessions", "", "", "", "", "", ""])

        sess_table = Table(rows, hAlign="LEFT", repeatRows=1)
        sess_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ]))
        story.append(sess_table)

        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | KneeConnect",
            ParagraphStyle("Footer", parent=normal_style, textColor=colors.grey, fontSize=8)
        ))

        doc.build(story)
        return out
    except Exception as e:
        print(f"reports._monthly_pdf error: {e}")
        import traceback; traceback.print_exc()
        return None


def _monthly_txt(patient_data, sessions, year, month, out: Path) -> Path | None:
    try:
        import calendar
        month_name = calendar.month_name[month]
        lines = [
            "=" * 60,
            f"KneeConnect — Monthly Report: {month_name} {year}",
            "=" * 60,
            "",
        ]
        lines += _patient_header_lines(patient_data)
        lines += ["", "-" * 60, "SUMMARY", "-" * 60]
        total   = len(sessions)
        correct = sum(s.get("correct_reps", 0) for s in sessions)
        secs    = sum(s.get("duration_seconds", 0) for s in sessions)
        best    = max((s.get("max_knee_angle", 0) for s in sessions), default=0)
        lines.append(f"Total sessions:  {total}")
        lines.append(f"Correct reps:    {correct}")
        lines.append(f"Total time:      {_secs_to_str(secs)}")
        lines.append(f"Best angle (°):  {best:.1f}")
        lines += ["", "-" * 60, "SESSIONS", "-" * 60]
        for s in sessions:
            lines.append(
                f"  {s.get('date','')} {s.get('time','')}  | {s.get('exercise','')}  "
                f"| {_secs_to_str(s.get('duration_seconds',0))}  "
                f"| {s.get('correct_reps',0)}/{s.get('total_reps',0)} reps  "
                f"| angle {s.get('min_knee_angle',0):.0f}°–{s.get('max_knee_angle',0):.0f}°"
            )
        if not sessions:
            lines.append("  No sessions this month.")
        lines += ["", "=" * 60,
                  f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | KneeConnect",
                  "=" * 60]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
    except Exception as e:
        print(f"reports._monthly_txt error: {e}")
        return None


# ─── Full Patient Record ──────────────────────────────────────────────────────

def generate_full_record(patient_data: dict, sessions: list) -> Path | None:
    """
    Generate a full patient record PDF (or .txt).
    Returns the output Path on success, or None on failure.
    """
    folder = get_reports_folder(patient_data)
    folder.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"full_record_{today}.pdf" if HAS_REPORTLAB else f"full_record_{today}.txt"
    output_path = folder / filename

    if HAS_REPORTLAB:
        return _full_record_pdf(patient_data, sessions, output_path)
    else:
        return _full_record_txt(patient_data, sessions, output_path)


def _full_record_pdf(patient_data: dict, sessions: list, out: Path) -> Path | None:
    try:
        doc = SimpleDocTemplate(str(out), pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        title_style  = ParagraphStyle("Title2",   parent=styles["Title"],   fontSize=18, spaceAfter=4)
        h2_style     = ParagraphStyle("Heading2B", parent=styles["Heading2"], fontSize=13, spaceAfter=4)
        normal_style = styles["Normal"]
        normal_style.fontSize = 10
        small_style  = ParagraphStyle("Small", parent=normal_style, fontSize=9, textColor=colors.HexColor("#555555"))

        story = []
        story.append(Paragraph("KneeConnect — Full Patient Record", title_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", small_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1abc9c")))
        story.append(Spacer(1, 0.4*cm))

        # ── Patient profile ──────────────────────────────────────────────────
        story.append(Paragraph("Patient Profile", h2_style))
        fields = [
            ("Name",              patient_data.get("name", "—")),
            ("ID",                patient_data.get("id", "—")),
            ("Age",               patient_data.get("age", "—")),
            ("Gender",            patient_data.get("gender", "—")),
            ("Mobile",            patient_data.get("mobile", "—")),
            ("Surgeon",           patient_data.get("surgeon", "—")),
            ("Physiotherapist",   patient_data.get("physio", "—")),
            ("Height (cm)",       patient_data.get("height", "—")),
            ("Weight (kg)",       patient_data.get("weight", "—")),
            ("Surgery Date",      patient_data.get("surgery_date", "—")),
            ("Medical History",   patient_data.get("history", "—")),
            ("Functional Goals",  patient_data.get("goals", "—")),
            ("Nutrition Notes",   patient_data.get("nutrition", "—")),
            ("Medications",       patient_data.get("meds", "—")),
        ]
        profile_data = [[k, v] for k, v in fields]
        profile_table = Table(profile_data, colWidths=[5*cm, None], hAlign="LEFT")
        profile_table.setStyle(TableStyle([
            ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE",  (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",      (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(profile_table)
        story.append(Spacer(1, 0.4*cm))

        # ── Thresholds ───────────────────────────────────────────────────────
        thresholds = patient_data.get("thresholds", {})
        if thresholds:
            story.append(Paragraph("Exercise Thresholds", h2_style))
            th_data = [["Parameter", "Value"]] + [[k, str(v)] for k, v in thresholds.items()]
            th_table = Table(th_data, hAlign="LEFT")
            th_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1abc9c")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ]))
            story.append(th_table)
            story.append(Spacer(1, 0.4*cm))

        # ── Recorded videos ──────────────────────────────────────────────────
        videos = patient_data.get("videos", [])
        if videos:
            story.append(Paragraph(f"Recorded Videos ({len(videos)} total)", h2_style))
            vid_data = [["#", "Exercise Label", "Filename", "Knee Range", "Hip Range"]]
            for i, v in enumerate(videos, 1):
                ang = v.get("angles", {})
                knee_r = (f"{ang.get('knee_min',0):.0f}°–{ang.get('knee_max',0):.0f}°"
                          if ang else "—")
                hip_r  = (f"{ang.get('hip_min',0):.0f}°–{ang.get('hip_max',0):.0f}°"
                          if ang else "—")
                fname = Path(v.get("path", "")).name or "—"
                vid_data.append([str(i), v.get("exercise", "—"), fname, knee_r, hip_r])
            vid_table = Table(vid_data, hAlign="LEFT", repeatRows=1)
            vid_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ]))
            story.append(vid_table)
            story.append(Spacer(1, 0.4*cm))

        # ── Documents index ──────────────────────────────────────────────────
        documents = patient_data.get("documents", [])
        if documents:
            story.append(Paragraph(f"Documents ({len(documents)} on file)", h2_style))
            doc_data = [["Title", "Filename", "Date Added", "Description"]]
            for d in documents:
                doc_data.append([
                    d.get("title", "—"),
                    d.get("filename", "—"),
                    d.get("date_added", "—"),
                    d.get("description", ""),
                ])
            doc_table = Table(doc_data, hAlign="LEFT", repeatRows=1)
            doc_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1abc9c")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ]))
            story.append(doc_table)
            story.append(Spacer(1, 0.4*cm))

        # ── Session history summary ──────────────────────────────────────────
        story.append(Paragraph(f"Session History ({len(sessions)} sessions)", h2_style))
        if sessions:
            total_correct = sum(s.get("correct_reps", 0) for s in sessions)
            total_secs    = sum(s.get("duration_seconds", 0) for s in sessions)
            best_angle    = max((s.get("max_knee_angle", 0) for s in sessions), default=0)
            summary_data  = [
                ["Total Sessions", "Total Correct Reps", "Total Time", "Best Angle (°)"],
                [str(len(sessions)), str(total_correct), _secs_to_str(total_secs), f"{best_angle:.1f}"],
            ]
            s_table = Table(summary_data, hAlign="LEFT")
            s_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1abc9c")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE",   (0, 0), (-1, -1), 10),
            ]))
            story.append(s_table)
            story.append(Spacer(1, 0.3*cm))

            # Detailed session rows
            sh_data = [["Date", "Exercise", "Duration", "Correct/Total", "Angle Range"]]
            for s in reversed(sessions):
                sh_data.append([
                    s.get("date", "") + " " + s.get("time", ""),
                    s.get("exercise", ""),
                    _secs_to_str(s.get("duration_seconds", 0)),
                    f"{s.get('correct_reps',0)}/{s.get('total_reps',0)}",
                    f"{s.get('min_knee_angle',0):.0f}°–{s.get('max_knee_angle',0):.0f}°",
                ])
            sh_table = Table(sh_data, hAlign="LEFT", repeatRows=1)
            sh_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
                ("GRID",       (0, 0), (-1, -1), 0.3, colors.grey),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ]))
            story.append(sh_table)
        else:
            story.append(Paragraph("No sessions recorded yet.", normal_style))

        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        story.append(Paragraph(
            f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | KneeConnect",
            ParagraphStyle("Footer", parent=normal_style, textColor=colors.grey, fontSize=8)
        ))

        doc.build(story)
        return out
    except Exception as e:
        print(f"reports._full_record_pdf error: {e}")
        import traceback; traceback.print_exc()
        return None


def _full_record_txt(patient_data: dict, sessions: list, out: Path) -> Path | None:
    try:
        lines = [
            "=" * 60,
            "KneeConnect — Full Patient Record",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 60, "",
            "PATIENT PROFILE",
            "-" * 60,
        ]
        fields = [
            ("Name",            patient_data.get("name", "—")),
            ("ID",              patient_data.get("id", "—")),
            ("Age",             patient_data.get("age", "—")),
            ("Gender",          patient_data.get("gender", "—")),
            ("Surgeon",         patient_data.get("surgeon", "—")),
            ("Physiotherapist", patient_data.get("physio", "—")),
            ("Surgery Date",    patient_data.get("surgery_date", "—")),
            ("Medical History", patient_data.get("history", "—")),
            ("Goals",           patient_data.get("goals", "—")),
            ("Medications",     patient_data.get("meds", "—")),
        ]
        for k, v in fields:
            lines.append(f"  {k}: {v}")

        thresholds = patient_data.get("thresholds", {})
        if thresholds:
            lines += ["", "THRESHOLDS", "-" * 60]
            for k, v in thresholds.items():
                lines.append(f"  {k}: {v}")

        videos = patient_data.get("videos", [])
        if videos:
            lines += ["", f"RECORDED VIDEOS ({len(videos)})", "-" * 60]
            for i, v in enumerate(videos, 1):
                lines.append(f"  {i}. {v.get('exercise','—')}  →  {Path(v.get('path','')).name}")

        documents = patient_data.get("documents", [])
        if documents:
            lines += ["", f"DOCUMENTS ({len(documents)})", "-" * 60]
            for d in documents:
                lines.append(f"  {d.get('title','—')}  |  {d.get('filename','—')}  |  {d.get('date_added','—')}")

        lines += ["", f"SESSION HISTORY ({len(sessions)} sessions)", "-" * 60]
        for s in sessions:
            lines.append(
                f"  {s.get('date','')} {s.get('time','')}  | {s.get('exercise','')}  "
                f"| {_secs_to_str(s.get('duration_seconds',0))}  "
                f"| {s.get('correct_reps',0)}/{s.get('total_reps',0)} reps"
            )
        if not sessions:
            lines.append("  No sessions yet.")

        lines += ["", "=" * 60]
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
    except Exception as e:
        print(f"reports._full_record_txt error: {e}")
        return None
