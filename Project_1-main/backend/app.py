# -*- coding: utf-8 -*-
import os
import sys
import json
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv

# Ensure root and backend .env are loaded first before any service initialization
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for env_candidate in [PROJECT_ROOT / ".env", BASE_DIR / ".env", BASE_DIR / "config" / ".env.example"]:
    if env_candidate.exists():
        load_dotenv(dotenv_path=str(env_candidate), override=False)

from orchestrator.orchestrator import GLOBAL_ORCHESTRATOR, SehatOrchestrator
from session_store.session_store import GLOBAL_SESSION_STORE, SehatSessionState
from session_store.patient_registry import GLOBAL_PATIENT_REGISTRY
from emergency.emergency_detector import GLOBAL_EMERGENCY_DETECTOR, EmergencyDetector
from doctor_delivery.doctor_service import GLOBAL_DOCTOR_DELIVERY, DoctorDeliveryService
from audit.audit_logger import GLOBAL_AUDIT_LOGGER
from audio_pipeline.cura_clinical_flow import GLOBAL_CURA_SESSIONS
from database.db_manager import GLOBAL_DB
from fastapi import WebSocket, WebSocketDisconnect

EMERGENCY_ALERTS_FEED = GLOBAL_DOCTOR_DELIVERY.emergency_feed

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    for candidate in [config_path, "backend/config.yaml", "../config.yaml", str(BASE_DIR / "config.yaml")]:
        if os.path.exists(candidate):
            try:
                import yaml
                with open(candidate, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sehat_app")

app = FastAPI(
    title="Diabetes Dost — AI Voice Pre-Screener for Diabetes",
    description="Context-aware diabetes pre-screening voice assistant in Hindi speech with dynamic question selection, independent emergency detection, and clinician triage summaries.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve static directory (support both root/static and backend/static)
STATIC_DIR = PROJECT_ROOT / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon_endpoint():
    fav_candidate = STATIC_DIR / "diabetes_dost_logo.png"
    if fav_candidate.exists():
        return FileResponse(fav_candidate, media_type="image/png")
    return FileResponse(STATIC_DIR / "favicon.ico")

training_state = {
    "is_training": False,
    "status": "idle",
    "current_epoch": 0,
    "total_epochs": 0,
    "best_wer": None,
    "latest_metrics": {},
    "error": None,
    "logs": []
}

class TranscriptUpdateRequest(BaseModel):
    id: str
    corrected_transcript: str
    review_status: str
    verified_by_human: bool = True

class PipelineConfigUpdate(BaseModel):
    sarvam_api_key: Optional[str] = None
    language_code: Optional[str] = None
    batch_size: Optional[int] = None
    num_epochs: Optional[int] = None
    learning_rate: Optional[float] = None

for folder in [
    "datasets/raw_audio", "datasets/processed_audio", "datasets/transcripts", 
    "datasets/manifests", "datasets/reviewed", "outputs/checkpoints", 
    "outputs/logs", "outputs/reports", "outputs/reports/sessions"
]:
    Path(folder).mkdir(parents=True, exist_ok=True)


# ==========================================
# GENERAL & AUDIO API ENDPOINTS
# ==========================================

@app.get("/favicon.ico")
async def favicon():
    fav = Path("static/favicon.ico")
    if fav.exists():
        return FileResponse(str(fav), media_type="image/x-icon")
    return FileResponse("static/dmh_logo.png", media_type="image/png")


@app.get("/api/health")
async def health_check():
    try:
        import torch
        cuda_ok = torch.cuda.is_available() if torch is not None else False
        gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "CPU Mode"
    except Exception:
        cuda_ok = False
        gpu_name = "CPU Mode"
    return {
        "status": "online",
        "app_name": "Diabetes Dost — AI Voice Pre-Screener for Diabetes",
        "hospital_name": "Deenanath Mangeshkar Hospital",
        "motto": "॥ आरोग्यक्षेमं वहाम्यहम् ॥",
        "bot_name": "Diabetes Dost",
        "language": "hi-IN",
        "voice_gender": "Male",
        "cuda_available": cuda_ok,
        "gpu_name": gpu_name,
        "active_sessions": len(GLOBAL_SESSION_STORE.sessions),
        "sarvam_configured": bool(os.getenv("SARVAM_API_KEY") and os.getenv("SARVAM_API_KEY") != "your_sarvam_api_key_here")
    }


@app.get("/api/config")
async def get_config():
    cfg = load_config()
    key = os.getenv("SARVAM_API_KEY", "")
    masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else ("Configured" if key else "Not Set")
    return {
        "config": cfg,
        "sarvam_api_key_status": masked_key
    }


@app.get("/api/audio/stream/{filename}")
async def stream_audio(filename: str):
    for folder in ["outputs/reports", "datasets/processed_audio", "datasets/raw_audio"]:
        target = Path(folder) / filename
        if target.exists():
            return FileResponse(
                str(target),
                media_type="audio/wav",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    raise HTTPException(status_code=404, detail="Audio file not found")


# ==========================================
# SEHAT AI VOICE PRE-SCREENER API ENDPOINTS
# ==========================================

@app.post("/api/sehat/session/start")
@app.post("/api/cura/session/start")
async def start_sehat_voice_session(session_id: Optional[str] = Form(None)):
    res = GLOBAL_ORCHESTRATOR.start_session(session_id=session_id)
    return JSONResponse(content=res)


@app.post("/api/sehat/session/start_followup")
@app.post("/api/cura/session/start_followup")
async def start_sehat_followup_session(
    patient_name: str = Form(...),
    session_id: Optional[str] = Form(None)
):
    res = GLOBAL_ORCHESTRATOR.start_followup_session(patient_name_or_id=patient_name, session_id=session_id)
    return JSONResponse(content=res)


@app.get("/api/patients/list")
async def list_registered_patients():
    patients = GLOBAL_PATIENT_REGISTRY.list_all_patients()
    return {
        "status": "success",
        "count": len(patients),
        "patients": patients
    }


@app.get("/api/patients/{patient_name_or_id}/history")
async def get_patient_history(patient_name_or_id: str):
    record = GLOBAL_PATIENT_REGISTRY.find_patient(patient_name_or_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Patient '{patient_name_or_id}' not found.")
    return {
        "status": "success",
        "patient": record
    }


@app.post("/api/sehat/session/turn")
@app.post("/api/cura/session/turn")
async def process_sehat_voice_turn(
    file: Optional[UploadFile] = File(None),
    session_id: str = Form(...),
    transcript: Optional[str] = Form(None)
):
    audio_bytes = None
    if file is not None:
        audio_bytes = await file.read()
    
    res = GLOBAL_ORCHESTRATOR.process_patient_turn(
        session_id=session_id,
        transcript_text=transcript,
        audio_bytes=audio_bytes
    )
    return JSONResponse(content=res)


@app.get("/api/sehat/session/{session_id}/summary")
@app.get("/api/cura/session/{session_id}/summary")
async def get_sehat_session_summary(session_id: str):
    summary = GLOBAL_ORCHESTRATOR.get_session_summary(session_id)
    if not summary:
        db_record = GLOBAL_DB.get_consultation_details(session_id)
        if db_record and db_record.get("full_data"):
            return {
                "status": "success",
                "summary": db_record["full_data"]
            }
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    GLOBAL_DB.save_consultation(summary)
    return {
        "status": "success",
        "summary": summary
    }


@app.get("/api/sehat/session/{session_id}/download")
@app.get("/api/cura/session/{session_id}/download")
async def download_sehat_session_report(session_id: str):
    summary = GLOBAL_ORCHESTRATOR.get_session_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    
    txt_file = summary.get("summary_file_txt")
    if txt_file and os.path.exists(txt_file):
        p_name = summary.get("patient", {}).get("name") or "Patient"
        filename = f"Summary_{p_name}_{session_id}.txt"
        return FileResponse(txt_file, media_type="text/plain; charset=utf-8", filename=filename)
    
    # Fallback to narrative text
    narrative = summary.get("clinical_summary_en", "") + "\n\n" + summary.get("clinical_summary_hi", "")
    return HTMLResponse(content=narrative, media_type="text/plain; charset=utf-8")


@app.get("/api/sehat/session/{session_id}/download/json")
async def download_sehat_session_json(session_id: str):
    summary = GLOBAL_ORCHESTRATOR.get_session_summary(session_id)
    if not summary:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    
    json_file = summary.get("summary_file_json")
    if json_file and os.path.exists(json_file):
        p_name = summary.get("patient", {}).get("name") or "Patient"
        filename = f"Summary_{p_name}_{session_id}.json"
        return FileResponse(json_file, media_type="application/json", filename=filename)
    
    return JSONResponse(content=summary)


@app.get("/api/sehat/summaries")
async def list_all_patient_summaries():
    """Lists all saved patient summary reports."""
    summaries_dir = "outputs/reports/summaries"
    results = []
    if os.path.exists(summaries_dir):
        for f in sorted(os.listdir(summaries_dir), reverse=True):
            if f.endswith(".json"):
                fpath = os.path.join(summaries_dir, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as jf:
                        data = json.load(jf)
                        results.append({
                            "session_id": data.get("session_id"),
                            "patient": data.get("patient"),
                            "branch": data.get("branch"),
                            "recommended_urgency": data.get("recommended_urgency"),
                            "generated_at": data.get("generated_at"),
                            "summary_file_txt": data.get("summary_file_txt"),
                            "summary_file_json": data.get("summary_file_json")
                        })
                except Exception:
                    pass
    return {
        "status": "success",
        "total": len(results),
        "summaries": results
    }


@app.get("/api/sehat/emergencies")
@app.get("/api/cura/emergencies")
async def get_sehat_emergency_alerts():
    emergencies = GLOBAL_DOCTOR_DELIVERY.get_emergency_feed()
    return {
        "status": "success",
        "count": len(emergencies),
        "emergencies": emergencies
    }


@app.get("/api/sehat/sessions")
@app.get("/api/cura/sessions")
async def list_all_sehat_sessions():
    sessions_list = GLOBAL_DOCTOR_DELIVERY.get_doctor_queue()
    if not sessions_list:
        sessions_list = GLOBAL_SESSION_STORE.list_all_sessions()
    return {
        "status": "success",
        "total": len(sessions_list),
        "sessions": sessions_list
    }


@app.get("/api/sehat/audit/{session_id}")
async def get_session_audit_log(session_id: str):
    events = GLOBAL_AUDIT_LOGGER.get_session_events(session_id)
    return {
        "status": "success",
        "session_id": session_id,
        "count": len(events),
        "events": events
    }


# ==========================================
# WEBSOCKET REAL-TIME STREAMING ENDPOINT
# ==========================================

@app.websocket("/ws/session")
async def websocket_session_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = None
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            event_type = msg.get("event")
            
            if event_type == "SESSION_START":
                session_id = msg.get("session_id")
                start_res = GLOBAL_ORCHESTRATOR.start_session(session_id)
                session_id = start_res["session_id"]
                await websocket.send_json({
                    "event": "SESSION_STARTED",
                    "data": start_res
                })
                
            elif event_type in ["AUDIO_CHUNK", "ASR_FINAL", "PATIENT_TURN"]:
                transcript = msg.get("transcript", "")
                sid = msg.get("session_id") or session_id
                
                await websocket.send_json({"event": "AI_THINKING", "session_id": sid})
                
                turn_res = GLOBAL_ORCHESTRATOR.process_patient_turn(
                    session_id=sid,
                    transcript_text=transcript
                )
                
                await websocket.send_json({
                    "event": "AI_RESPONSE",
                    "data": turn_res
                })
                
                if turn_res.get("is_emergency"):
                    await websocket.send_json({
                        "event": "EMERGENCY_DETECTED",
                        "data": turn_res
                    })
                elif turn_res.get("is_completed"):
                    await websocket.send_json({
                        "event": "SESSION_COMPLETED",
                        "data": turn_res
                    })
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"event": "SESSION_ERROR", "error": str(e)})
        except Exception:
            pass


# ==========================================
# MODERN WEB APP & ADMIN PORTAL
# ==========================================
TEMPLATES_DIR = Path(__file__).parent / "templates"
INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"
ADMIN_HTML_PATH = TEMPLATES_DIR / "admin.html"

class AdminLoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest):
    auth_res = GLOBAL_DB.authenticate_admin(req.username, req.password)
    if not auth_res:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {
        "status": "success",
        "message": "Authentication successful",
        "token": auth_res["token"],
        "user": {
            "username": auth_res["username"],
            "full_name": auth_res["full_name"],
            "role": auth_res["role"]
        }
    }

@app.get("/api/admin/check-auth")
async def check_admin_auth(token: Optional[str] = None):
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required.")
    user = GLOBAL_DB.verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return {"status": "success", "user": user}

@app.post("/api/admin/logout")
async def admin_logout(token: Optional[str] = Form(None)):
    if token:
        GLOBAL_DB.invalidate_token(token)
    return {"status": "success", "message": "Logged out successfully."}

@app.get("/api/admin/metrics")
async def get_admin_metrics():
    metrics = GLOBAL_DB.get_dashboard_metrics()
    return {"status": "success", "metrics": metrics}

@app.get("/api/admin/consultations")
async def list_admin_consultations(
    search: Optional[str] = None,
    urgency: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    res = GLOBAL_DB.get_consultations(search=search, urgency=urgency, limit=limit, offset=offset)
    return {"status": "success", "data": res}

@app.get("/api/admin/consultations/{session_id}")
async def get_admin_consultation_detail(session_id: str):
    record = GLOBAL_DB.get_consultation_details(session_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Consultation '{session_id}' not found.")
    return {"status": "success", "consultation": record}

@app.delete("/api/admin/consultations/{session_id}")
async def delete_admin_consultation(session_id: str):
    deleted = GLOBAL_DB.delete_consultation(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Consultation '{session_id}' not found.")
    return {"status": "success", "message": "Consultation deleted successfully."}

@app.get("/", response_class=HTMLResponse)
async def serve_cura_app():
    if INDEX_HTML_PATH.exists():
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Index template not found</h1>", status_code=404)

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_portal():
    if ADMIN_HTML_PATH.exists():
        with open(ADMIN_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Admin template not found</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

