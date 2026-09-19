# -*- coding: utf-8 -*-
import os
import json
import sqlite3
import hashlib
import secrets
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("sehat_db")

DB_DIR = Path(__file__).resolve().parent.parent / "outputs" / "database"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "diabetes_dost.db"

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Hash password using PBKDF2 HMAC SHA256."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return f"{salt}${pw_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt$hash."""
    try:
        salt, expected_hash = stored_hash.split("$", 1)
        test_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return secrets.compare_digest(test_hash, expected_hash)
    except Exception:
        return False

class DatabaseManager:
    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()
        self._seed_default_admin()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Admins table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT DEFAULT 'admin',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Consultations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS consultations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    patient_name TEXT,
                    patient_id TEXT,
                    age INTEGER,
                    gender TEXT,
                    diabetes_type TEXT,
                    branch TEXT,
                    recommended_urgency TEXT DEFAULT 'routine',
                    is_emergency BOOLEAN DEFAULT 0,
                    summary_en TEXT,
                    summary_hi TEXT,
                    qa_transcript_json TEXT,
                    full_data_json TEXT,
                    summary_file_txt TEXT,
                    summary_file_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Sessions tokens / active logins table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS admin_tokens (
                    token TEXT PRIMARY KEY,
                    admin_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(admin_id) REFERENCES admins(id)
                );
            """)
            conn.commit()

    def _seed_default_admin(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM admins WHERE username = 'admin'")
            row = cursor.fetchone()
            if not row:
                pw_hash = hash_password("admin123")
                cursor.execute(
                    "INSERT INTO admins (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                    ("admin", pw_hash, "System Administrator", "superadmin")
                )
                conn.commit()
                logger.info("Initialized default admin account (username: admin)")

    def authenticate_admin(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify admin login and return user profile + token if successful."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password_hash, full_name, role FROM admins WHERE username = ?", (username.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            if verify_password(password, row["password_hash"]):
                token = secrets.token_hex(32)
                cursor.execute("INSERT INTO admin_tokens (token, admin_id) VALUES (?, ?)", (token, row["id"]))
                conn.commit()
                return {
                    "admin_id": row["id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "role": row["role"],
                    "token": token
                }
        return None

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.id, a.username, a.full_name, a.role 
                FROM admin_tokens t 
                JOIN admins a ON t.admin_id = a.id 
                WHERE t.token = ?
            """, (token,))
            row = cursor.fetchone()
            if row:
                return {
                    "admin_id": row["id"],
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "role": row["role"]
                }
        return None

    def invalidate_token(self, token: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admin_tokens WHERE token = ?", (token,))
            conn.commit()

    def save_live_session(self, state_or_data: Any) -> bool:
        """Immediately save or update a real-time active consultation session in SQLite DB."""
        if not state_or_data:
            return False
        
        if hasattr(state_or_data, "to_dict"):
            d = state_or_data.to_dict()
        elif isinstance(state_or_data, dict):
            d = state_or_data
        else:
            return False

        session_id = d.get("session_id")
        if not session_id:
            return False

        patient = d.get("patient", {}) or d.get("demographics", {})
        patient_name = patient.get("name") or d.get("patient_name") or "Patient"
        patient_id = patient.get("patient_id") or d.get("patient_id") or f"PAT-{session_id[-4:].upper()}"
        age = patient.get("age")
        gender = patient.get("gender") or patient.get("sex") or ""
        diabetes_type = d.get("diabetes_type") or patient.get("diabetes_type") or ("Type 2 Diabetes" if d.get("branch") == "known_diabetic" else "Screening")
        branch = d.get("branch") or "common"
        urgency = d.get("recommended_urgency") or "routine"
        is_emergency = 1 if urgency == "emergency" or d.get("is_emergency") or d.get("emergency_escalation") else 0

        # Build clean QA transcript from answers list in real-time
        raw_answers = d.get("answers", [])
        qa_list = []
        for ans in raw_answers:
            qa_list.append({
                "question_id": ans.get("question_id"),
                "question_asked_hi": ans.get("question_asked_hi"),
                "patient_answer_hi": ans.get("patient_answer_hi"),
                "timestamp": ans.get("timestamp")
            })

        qa_json = json.dumps(qa_list, ensure_ascii=False)
        full_json = json.dumps(d, ensure_ascii=False)
        created_at = d.get("created_at") or datetime.now(timezone.utc).isoformat()

        # Check existing summary if already generated
        existing = self.get_consultation_details(session_id)
        summary_en = (existing.get("summary_en") if existing else "") or d.get("clinical_summary_en") or d.get("summary_narrative") or "Consultation in progress..."
        summary_hi = (existing.get("summary_hi") if existing else "") or d.get("clinical_summary_hi") or "परामर्श सुरू आहे..."
        txt_file = (existing.get("summary_file_txt") if existing else "") or d.get("summary_file_txt") or ""
        json_file = (existing.get("summary_file_json") if existing else "") or d.get("summary_file_json") or ""

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO consultations (
                    session_id, patient_name, patient_id, age, gender, diabetes_type,
                    branch, recommended_urgency, is_emergency, summary_en, summary_hi,
                    qa_transcript_json, full_data_json, summary_file_txt, summary_file_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    patient_name=excluded.patient_name,
                    patient_id=excluded.patient_id,
                    age=excluded.age,
                    gender=excluded.gender,
                    diabetes_type=excluded.diabetes_type,
                    branch=excluded.branch,
                    recommended_urgency=excluded.recommended_urgency,
                    is_emergency=excluded.is_emergency,
                    qa_transcript_json=excluded.qa_transcript_json,
                    full_data_json=excluded.full_data_json
            """, (
                session_id, patient_name, patient_id, age, gender, diabetes_type,
                branch, urgency, is_emergency, summary_en, summary_hi,
                qa_json, full_json, txt_file, json_file, created_at
            ))
            conn.commit()
            return True

    def save_consultation(self, summary_data: Dict[str, Any]) -> bool:
        """Insert or update a consultation summary record."""
        session_id = summary_data.get("session_id")
        if not session_id:
            return False

        patient = summary_data.get("patient", {}) or summary_data.get("demographics", {})
        patient_name = patient.get("name") or summary_data.get("patient_name") or "Patient"
        patient_id = patient.get("patient_id") or summary_data.get("patient_id") or f"PAT-{session_id[-4:].upper()}"
        age = patient.get("age")
        gender = patient.get("gender") or patient.get("sex") or ""
        diabetes_type = summary_data.get("diabetes_type") or patient.get("diabetes_type") or ""
        branch = summary_data.get("branch") or "common"
        urgency = summary_data.get("recommended_urgency") or "routine"
        is_emergency = 1 if urgency == "emergency" or summary_data.get("is_emergency") else 0
        summary_en = summary_data.get("clinical_summary_en") or summary_data.get("summary_narrative") or ""
        summary_hi = summary_data.get("clinical_summary_hi") or ""
        qa_json = json.dumps(summary_data.get("qa_transcript", summary_data.get("answers", [])), ensure_ascii=False)
        full_json = json.dumps(summary_data, ensure_ascii=False)
        txt_file = summary_data.get("summary_file_txt") or ""
        json_file = summary_data.get("summary_file_json") or ""
        created_at = summary_data.get("generated_at") or summary_data.get("created_at") or datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO consultations (
                    session_id, patient_name, patient_id, age, gender, diabetes_type,
                    branch, recommended_urgency, is_emergency, summary_en, summary_hi,
                    qa_transcript_json, full_data_json, summary_file_txt, summary_file_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    patient_name=excluded.patient_name,
                    patient_id=excluded.patient_id,
                    age=excluded.age,
                    gender=excluded.gender,
                    diabetes_type=excluded.diabetes_type,
                    branch=excluded.branch,
                    recommended_urgency=excluded.recommended_urgency,
                    is_emergency=excluded.is_emergency,
                    summary_en=excluded.summary_en,
                    summary_hi=excluded.summary_hi,
                    qa_transcript_json=excluded.qa_transcript_json,
                    full_data_json=excluded.full_data_json,
                    summary_file_txt=excluded.summary_file_txt,
                    summary_file_json=excluded.summary_file_json,
                    created_at=excluded.created_at
            """, (
                session_id, patient_name, patient_id, age, gender, diabetes_type,
                branch, urgency, is_emergency, summary_en, summary_hi,
                qa_json, full_json, txt_file, json_file, created_at
            ))
            conn.commit()
            return True

    def get_consultations(
        self,
        search: Optional[str] = None,
        urgency: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Fetch list of consultations with filters and pagination."""
        query = "SELECT * FROM consultations WHERE 1=1"
        params = []

        if search:
            query += " AND (patient_name LIKE ? OR session_id LIKE ? OR patient_id LIKE ?)"
            s_param = f"%{search.strip()}%"
            params.extend([s_param, s_param, s_param])

        if urgency and urgency.lower() != "all":
            query += " AND LOWER(recommended_urgency) = ?"
            params.append(urgency.strip().lower())

        # Count total
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()
            consultations = []
            for r in rows:
                consultations.append({
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "patient_name": r["patient_name"],
                    "patient_id": r["patient_id"],
                    "age": r["age"],
                    "gender": r["gender"],
                    "diabetes_type": r["diabetes_type"],
                    "branch": r["branch"],
                    "recommended_urgency": r["recommended_urgency"],
                    "is_emergency": bool(r["is_emergency"]),
                    "summary_en": r["summary_en"],
                    "summary_hi": r["summary_hi"],
                    "summary_file_txt": r["summary_file_txt"],
                    "summary_file_json": r["summary_file_json"],
                    "created_at": r["created_at"]
                })

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "consultations": consultations
            }

    def get_consultation_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM consultations WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            qa = []
            if row["qa_transcript_json"]:
                try:
                    qa = json.loads(row["qa_transcript_json"])
                except Exception:
                    pass

            full_data = {}
            if row["full_data_json"]:
                try:
                    full_data = json.loads(row["full_data_json"])
                except Exception:
                    pass

            return {
                "id": row["id"],
                "session_id": row["session_id"],
                "patient_name": row["patient_name"],
                "patient_id": row["patient_id"],
                "age": row["age"],
                "gender": row["gender"],
                "diabetes_type": row["diabetes_type"],
                "branch": row["branch"],
                "recommended_urgency": row["recommended_urgency"],
                "is_emergency": bool(row["is_emergency"]),
                "summary_en": row["summary_en"],
                "summary_hi": row["summary_hi"],
                "qa_transcript": qa,
                "full_data": full_data,
                "summary_file_txt": row["summary_file_txt"],
                "summary_file_json": row["summary_file_json"],
                "created_at": row["created_at"]
            }

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Aggregate stats for the admin dashboard."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM consultations")
            total_consultations = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM consultations WHERE is_emergency = 1 OR recommended_urgency = 'emergency'")
            emergencies = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM consultations WHERE recommended_urgency = 'routine'")
            routine = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT patient_name) FROM consultations WHERE patient_name IS NOT NULL AND patient_name != ''")
            distinct_patients = cursor.fetchone()[0]

            return {
                "total_consultations": total_consultations,
                "emergency_cases": emergencies,
                "routine_reviews": routine,
                "total_patients": distinct_patients
            }

    def delete_consultation(self, session_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM consultations WHERE session_id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def sync_existing_json_summaries(self):
        """Auto-migrates JSON summaries from outputs/reports/summaries into SQLite."""
        summaries_dir = Path(__file__).resolve().parent.parent / "outputs" / "reports" / "summaries"
        if not summaries_dir.exists():
            return
        
        count = 0
        for fname in os.listdir(summaries_dir):
            if fname.endswith(".json"):
                fpath = summaries_dir / fname
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and data.get("session_id"):
                            self.save_consultation(data)
                            count += 1
                except Exception as e:
                    logger.debug(f"Sync skip {fname}: {e}")
        if count > 0:
            logger.info(f"Synced {count} consultation summaries into SQLite database.")

GLOBAL_DB = DatabaseManager()
