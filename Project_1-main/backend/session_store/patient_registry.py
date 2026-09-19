import os
import re
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("sehat_patient_registry")

class PatientRegistry:
    """
    Patient Longitudinal Health Record (EHR) Registry for Diabetes Dost AI.
    Saves patient baseline demographics, diabetes history, past visit summaries,
    blood sugar trends, and past medications across regular follow-up visits.
    """
    def __init__(self, registry_dir: str = "outputs/reports/patients"):
        self.registry_dir = registry_dir
        self.lock = threading.RLock()
        os.makedirs(self.registry_dir, exist_ok=True)
        self._index = self._build_index()

    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""
        clean = re.sub(r"[^\w\u0900-\u097F]", "", name.lower().strip())
        return clean

    def _sanitize_filename(self, name: str) -> str:
        clean = re.sub(r"[^\w\-_]", "_", name.strip())
        return clean or "patient"

    def _build_index(self) -> Dict[str, str]:
        index = {}
        if not os.path.exists(self.registry_dir):
            return index
        for fname in os.listdir(self.registry_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self.registry_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        p_name = data.get("name", "")
                        norm_name = self._normalize_name(p_name)
                        p_id = data.get("patient_id", "")
                        if norm_name:
                            index[norm_name] = fpath
                        if p_id:
                            index[p_id.lower()] = fpath
                except Exception as e:
                    logger.warning(f"Failed to read patient file {fname}: {e}")
        return index

    def find_patient(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Look up a patient record by full/partial name or patient ID."""
        if not name_or_id:
            return None
        with self.lock:
            key = self._normalize_name(name_or_id)
            if key in self._index:
                try:
                    with open(self._index[key], "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

            # Try prefix / substring match for returning patients
            for idx_key, fpath in self._index.items():
                if key and (key in idx_key or idx_key in key):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        pass
        return None

    def save_patient_visit(self, session_state) -> Dict[str, Any]:
        """Update or create a patient's longitudinal record after a completed session."""
        d = session_state.demographics or {}
        p_name = d.get("name", "").strip()
        if not p_name:
            return {}

        with self.lock:
            existing = self.find_patient(p_name)
            p_id = existing.get("patient_id") if existing else f"DMH_PAT_{re.sub(r'[^a-zA-Z0-9]', '', p_name)[:6].upper()}_{int(datetime.now().timestamp()) % 10000:04d}"

            now_iso = datetime.now(timezone.utc).isoformat()

            # Past visits log
            past_visits = existing.get("past_visits", []) if existing else []

            # Extract recent sugar from this visit
            sugars = session_state.blood_sugar_readings or []
            current_sugar = sugars[-1]["value"] if sugars else None

            visit_entry = {
                "session_id": session_state.session_id,
                "visit_date": now_iso,
                "branch": session_state.branch,
                "diabetes_type": getattr(session_state, "diabetes_type", None),
                "blood_sugar_reading": current_sugar,
                "symptoms_reported": session_state.symptoms_reported,
                "medications": session_state.medications,
                "recommended_urgency": session_state.recommended_urgency,
                "summary_narrative": getattr(session_state, "generated_summary", {}).get("summary_narrative") if getattr(session_state, "generated_summary", None) else None
            }

            # Avoid duplicate visit entries for same session
            if not any(v.get("session_id") == session_state.session_id for v in past_visits):
                past_visits.append(visit_entry)

            # Build aggregated patient profile
            patient_record = {
                "patient_id": p_id,
                "name": p_name,
                "age": d.get("age") or (existing.get("age") if existing else None),
                "gender": d.get("gender") or (existing.get("gender") if existing else None),
                "branch": session_state.branch if session_state.branch != "follow_up" else (existing.get("branch") if existing else "known_diabetic"),
                "diabetes_type": getattr(session_state, "diabetes_type", None) or (existing.get("diabetes_type") if existing else None),
                "baseline_diabetes_duration": session_state.diabetes_history or (existing.get("baseline_diabetes_duration") if existing else None),
                "family_history": session_state.family_history if session_state.family_history is not None else (existing.get("family_history") if existing else None),
                "active_medications": session_state.medications if session_state.medications else (existing.get("active_medications", []) if existing else []),
                "last_blood_sugar": current_sugar if current_sugar is not None else (existing.get("last_blood_sugar") if existing else None),
                "total_visits_count": len(past_visits),
                "first_visit_date": existing.get("first_visit_date", now_iso) if existing else now_iso,
                "last_visit_date": now_iso,
                "past_visits": past_visits
            }

            # Persist to disk
            safe_name = self._sanitize_filename(p_name)
            filename = f"Patient_{safe_name}_{p_id}.json"
            filepath = os.path.join(self.registry_dir, filename)

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(patient_record, f, ensure_ascii=False, indent=2)

                norm_name = self._normalize_name(p_name)
                self._index[norm_name] = filepath
                self._index[p_id.lower()] = filepath
                logger.info(f"Saved patient record for '{p_name}' (ID: {p_id}) to {filepath}")
            except Exception as e:
                logger.error(f"Failed to persist patient record for '{p_name}': {e}")

            return patient_record

    def list_all_patients(self) -> List[Dict[str, Any]]:
        """List all registered patients with summary stats for UI selection."""
        patients = []
        seen_ids = set()
        with self.lock:
            for fpath in set(self._index.values()):
                if os.path.exists(fpath):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            p = json.load(f)
                            pid = p.get("patient_id")
                            if pid and pid not in seen_ids:
                                seen_ids.add(pid)
                                patients.append({
                                    "patient_id": pid,
                                    "name": p.get("name", "Unknown"),
                                    "age": p.get("age"),
                                    "gender": p.get("gender"),
                                    "branch": p.get("branch"),
                                    "diabetes_type": p.get("diabetes_type"),
                                    "last_blood_sugar": p.get("last_blood_sugar"),
                                    "total_visits_count": p.get("total_visits_count", 1),
                                    "last_visit_date": p.get("last_visit_date")
                                })
                    except Exception:
                        pass
        # Sort by last visit descending
        patients.sort(key=lambda x: str(x.get("last_visit_date", "")), reverse=True)
        return patients


# Global instance
GLOBAL_PATIENT_REGISTRY = PatientRegistry()
