"""
storage.py — KneeConnect consistent per-patient storage helpers.

Canonical folder structure:
    patients_assets/
        <patient_id>/
            patient.json        <- profile + videos + thresholds + documents index
            sessions.json       <- all session records
            videos/             <- recorded MP4 files
            thumbs/             <- JPEG thumbnails
            documents/          <- uploaded PDFs / scans
            reports/            <- generated PDF reports
"""

import json
import os
import shutil
from pathlib import Path

ASSETS_DIR = "patients_assets"


# ─── ID helpers ─────────────────────────────────────────────────────────────

def get_patient_id(patient_data: dict) -> str:
    """Return a stable folder-safe ID for this patient."""
    pid = str(patient_data.get("id", "")).strip()
    if not pid:
        name = patient_data.get("name", "unknown").replace(" ", "_")
        pid = name if name else "unknown"
    return pid


def get_patient_folder(patient_data: dict) -> Path:
    return Path(ASSETS_DIR) / get_patient_id(patient_data)


def ensure_patient_folder(patient_data: dict) -> Path:
    folder = get_patient_folder(patient_data)
    for sub in ("videos", "thumbs", "documents", "reports"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    return folder


# ─── Sessions ────────────────────────────────────────────────────────────────

def get_sessions_file(patient_data: dict) -> Path:
    return get_patient_folder(patient_data) / "sessions.json"


def load_sessions(patient_data: dict) -> list:
    """Load sessions for this patient. Auto-migrates old name-based files."""
    spath = get_sessions_file(patient_data)
    if spath.exists():
        try:
            with open(spath, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"storage.load_sessions error: {e}")
            return []
    # Try migrating from old {name}_sessions.json in CWD
    return _migrate_old_sessions(patient_data)


def save_session(patient_data: dict, session: dict) -> bool:
    """Append session to the patient's sessions.json. Returns True on success."""
    try:
        folder = ensure_patient_folder(patient_data)
        spath = get_sessions_file(patient_data)
        sessions = load_sessions(patient_data)
        sessions.append(session)
        with open(spath, "w") as f:
            json.dump(sessions, f, indent=2)
        return True
    except Exception as e:
        print(f"storage.save_session error: {e}")
        return False


def _migrate_old_sessions(patient_data: dict) -> list:
    """Import sessions from legacy {name}_sessions.json if it exists."""
    name = patient_data.get("name", "").replace(" ", "_")
    if not name:
        return []
    old_file = Path(f"{name}_sessions.json")
    if not old_file.exists():
        return []
    try:
        with open(old_file, "r") as f:
            sessions = json.load(f)
        # Persist to new location
        folder = ensure_patient_folder(patient_data)
        spath = get_sessions_file(patient_data)
        with open(spath, "w") as f:
            json.dump(sessions, f, indent=2)
        print(f"Migrated {len(sessions)} session(s) from {old_file} → {spath}")
        return sessions
    except Exception as e:
        print(f"storage._migrate_old_sessions error: {e}")
        return []


# ─── Patient JSON helpers ────────────────────────────────────────────────────

def load_patient_json(patient_data: dict) -> dict:
    """Load the full patient.json for this patient."""
    p = get_patient_folder(patient_data) / "patient.json"
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_patient_json(patient_data: dict, full_data: dict) -> bool:
    """Overwrite patient.json with full_data."""
    try:
        folder = ensure_patient_folder(patient_data)
        p = folder / "patient.json"
        with open(p, "w") as f:
            json.dump(full_data, f, indent=2)
        return True
    except Exception as e:
        print(f"storage.save_patient_json error: {e}")
        return False


def update_patient_json(patient_data: dict, updates: dict) -> bool:
    """Merge updates into patient.json (preserves existing keys)."""
    try:
        existing = load_patient_json(patient_data)
        existing.update(updates)
        return save_patient_json(patient_data, existing)
    except Exception as e:
        print(f"storage.update_patient_json error: {e}")
        return False


# ─── Documents ───────────────────────────────────────────────────────────────

def get_documents_folder(patient_data: dict) -> Path:
    folder = ensure_patient_folder(patient_data)
    return folder / "documents"


def add_document(patient_data: dict, src_path: str, title: str, description: str = "") -> bool:
    """Copy a file into the patient's documents folder and update the index."""
    try:
        doc_folder = get_documents_folder(patient_data)
        doc_folder.mkdir(parents=True, exist_ok=True)
        src = Path(src_path)
        dest = doc_folder / src.name
        # Avoid name collisions
        if dest.exists():
            stem, suffix = src.stem, src.suffix
            i = 1
            while dest.exists():
                dest = doc_folder / f"{stem}_{i}{suffix}"
                i += 1
        shutil.copy2(src_path, dest)

        # Update index in patient.json
        from datetime import datetime
        pj = load_patient_json(patient_data)
        docs = pj.get("documents", [])
        docs.append({
            "filename": dest.name,
            "path": str(dest),
            "title": title or src.name,
            "description": description,
            "date_added": datetime.now().strftime("%Y-%m-%d"),
        })
        pj["documents"] = docs
        return save_patient_json(patient_data, pj)
    except Exception as e:
        print(f"storage.add_document error: {e}")
        return False


def remove_document(patient_data: dict, filename: str) -> bool:
    """Delete a document file and remove it from the index."""
    try:
        doc_folder = get_documents_folder(patient_data)
        fpath = doc_folder / filename
        if fpath.exists():
            fpath.unlink()
        pj = load_patient_json(patient_data)
        pj["documents"] = [d for d in pj.get("documents", []) if d.get("filename") != filename]
        return save_patient_json(patient_data, pj)
    except Exception as e:
        print(f"storage.remove_document error: {e}")
        return False


# ─── Reports folder ──────────────────────────────────────────────────────────

def get_reports_folder(patient_data: dict) -> Path:
    folder = ensure_patient_folder(patient_data)
    return folder / "reports"
