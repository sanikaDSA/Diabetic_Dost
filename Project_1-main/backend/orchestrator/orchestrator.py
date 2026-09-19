import os
import io
import json
import logging
from typing import Dict, Any, Optional

from asr.asr_service import get_asr_service, ASRService
from tts.tts_service import get_tts_service, TTSService
from emergency.emergency_detector import GLOBAL_EMERGENCY_DETECTOR, EmergencyDetector
from dialogue.dialogue_manager import GLOBAL_DIALOGUE_MANAGER, DialogueManager
from summary.summary_generator import GLOBAL_SUMMARY_GENERATOR, SummaryGenerator
from doctor_delivery.doctor_service import GLOBAL_DOCTOR_DELIVERY, DoctorDeliveryService
from session_store.session_store import GLOBAL_SESSION_STORE, SessionStore
from session_store.patient_registry import GLOBAL_PATIENT_REGISTRY
from audit.audit_logger import GLOBAL_AUDIT_LOGGER

logger = logging.getLogger("sehat_orchestrator")

class SehatOrchestrator:
    """
    Central Orchestrator coordinating ASR, Emergency Detector, Dialogue Manager,
    TTS, Summary Generator, Doctor Delivery, and Audit Logger.
    """
    def __init__(
        self,
        asr_service: Optional[ASRService] = None,
        tts_service: Optional[TTSService] = None,
        emergency_detector: Optional[EmergencyDetector] = None,
        dialogue_manager: Optional[DialogueManager] = None,
        summary_generator: Optional[SummaryGenerator] = None,
        doctor_delivery: Optional[DoctorDeliveryService] = None
    ):
        self.asr = asr_service or get_asr_service()
        self.tts = tts_service or get_tts_service()
        self.emergency = emergency_detector or GLOBAL_EMERGENCY_DETECTOR
        self.dialogue = dialogue_manager or GLOBAL_DIALOGUE_MANAGER
        self.summary = summary_generator or GLOBAL_SUMMARY_GENERATOR
        self.doctor = doctor_delivery or GLOBAL_DOCTOR_DELIVERY

    def start_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Start a new session, synthesize mandatory Sehat AI intro."""
        state, greeting_text = self.dialogue.start_session(session_id)
        
        audio_filename = f"outputs/reports/sehat_greeting_{state.session_id}.wav"
        master_greeting = "outputs/reports/sehat_greeting_master.wav"
        if os.path.exists(master_greeting) and os.path.getsize(master_greeting) > 500:
            import shutil
            try:
                shutil.copyfile(master_greeting, audio_filename)
                audio_stream_url = f"/api/audio/stream/sehat_greeting_{state.session_id}.wav"
            except Exception:
                tts_res = self.tts.synthesize(greeting_text, output_path=audio_filename)
                audio_stream_url = f"/api/audio/stream/sehat_greeting_{state.session_id}.wav" if (os.path.exists(audio_filename) and os.path.getsize(audio_filename) > 500) else None
        else:
            tts_res = self.tts.synthesize(greeting_text, output_path=audio_filename)
            audio_stream_url = f"/api/audio/stream/sehat_greeting_{state.session_id}.wav" if (os.path.exists(audio_filename) and os.path.getsize(audio_filename) > 500) else None
            if os.path.exists(audio_filename) and os.path.getsize(audio_filename) > 500:
                import shutil
                try:
                    shutil.copyfile(audio_filename, master_greeting)
                except Exception:
                    pass

        # Save new session immediately to SQLite Consultations DB
        try:
            from database.db_manager import GLOBAL_DB
            GLOBAL_DB.save_live_session(state)
        except Exception:
            pass

        return {
            "status": "success",
            "event": "SESSION_STARTED",
            "session_id": state.session_id,
            "bot_speech_hi": greeting_text,
            "audio_url": audio_stream_url,
            "state": state.to_dict(),
            "questions_asked_count": state.questions_asked_count,
            "total_budget": state.max_budget,
            "branch": state.branch
        }

    def start_followup_session(self, patient_name_or_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Start a follow-up consultation for a returning registered patient."""
        state, greeting_text = self.dialogue.start_followup_session(patient_name_or_id, session_id)

        audio_filename = f"outputs/reports/sehat_fu_greeting_{state.session_id}.wav"
        tts_res = self.tts.synthesize(greeting_text, output_path=audio_filename)
        audio_stream_url = f"/api/audio/stream/sehat_fu_greeting_{state.session_id}.wav" if (os.path.exists(audio_filename) and os.path.getsize(audio_filename) > 500) else None

        # Save followup session immediately to SQLite Consultations DB
        try:
            from database.db_manager import GLOBAL_DB
            GLOBAL_DB.save_live_session(state)
        except Exception:
            pass

        return {
            "status": "success",
            "event": "FOLLOWUP_SESSION_STARTED",
            "session_id": state.session_id,
            "patient_name": state.demographics.get("name"),
            "bot_speech_hi": greeting_text,
            "audio_url": audio_stream_url,
            "state": state.to_dict(),
            "questions_asked_count": state.questions_asked_count,
            "total_budget": state.max_budget,
            "branch": state.branch
        }

    def process_patient_turn(
        self,
        session_id: str,
        transcript_text: Optional[str] = None,
        audio_bytes: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Process a patient turn either via text transcript or raw audio bytes.
        Performs parallel emergency check, dialogue progression, TTS synthesis, and summary persistence.
        """
        state = GLOBAL_SESSION_STORE.get_or_create(session_id)

        # 1. ASR Transcription if audio provided
        final_transcript = (transcript_text or "").strip()
        if not final_transcript and audio_bytes:
            asr_res = self.asr.transcribe(audio_bytes)
            final_transcript = asr_res.get("transcript", "").strip()

        if not final_transcript:
            return {
                "status": "empty_input",
                "event": "ASR_EMPTY",
                "session_id": session_id,
                "bot_speech_hi": "कृपया फिर से बोलिए, मैं सुन रहा हूँ।",
                "state": state.to_dict()
            }

        # 2. EMERGENCY DETECTION ON EVERY TURN
        is_emerg, emerg_event = self.emergency.scan(final_transcript, session_id=session_id)
        if is_emerg and emerg_event:
            state.emergency_escalation = True
            state.emergency_details = emerg_event
            state.is_completed = True
            state.recommended_urgency = "urgent"
            state.urgency_reasons = [f"Emergency: {', '.join(emerg_event.get('detected_signals', []))}"]

            # Record answer and log
            state.record_answer(
                question_id=state.current_question_id,
                question_hi="[EMERGENCY_INTERRUPTION]",
                patient_answer_hi=final_transcript
            )

            # Audit & Doctor Real-Time Alert
            GLOBAL_AUDIT_LOGGER.log_event(session_id, "EMERGENCY_DETECTED", emerg_event)
            self.doctor.push_emergency_alert(emerg_event)

            # Generate Final Summary and Update Patient Registry
            summary_res = self.summary.generate(state)
            GLOBAL_PATIENT_REGISTRY.save_patient_visit(state)
            self.doctor.push_completed_summary(summary_res)
            GLOBAL_SESSION_STORE.save(state)
            try:
                from database.db_manager import GLOBAL_DB
                GLOBAL_DB.save_consultation(summary_res)
            except Exception:
                pass

            emerg_speech = emerg_event.get("verbal_instruction_hi", "")
            emerg_audio_file = f"outputs/reports/sehat_emergency_{session_id}.wav"
            tts_res = self.tts.synthesize(emerg_speech, output_path=emerg_audio_file)

            return {
                "status": "emergency_interrupted",
                "event": "EMERGENCY_DETECTED",
                "session_id": session_id,
                "is_emergency": True,
                "emergency_event": emerg_event,
                "bot_speech_hi": emerg_speech,
                "audio_url": tts_res.get("audio_url") or f"/api/audio/stream/sehat_emergency_{session_id}.wav",
                "is_completed": True,
                "state": state.to_dict()
            }

        # 3. NORMAL DIALOGUE TURN
        dialogue_res = self.dialogue.process_turn(session_id, final_transcript)
        bot_speech = dialogue_res.get("bot_speech_hi", "")
        is_completed = dialogue_res.get("is_completed", False)

        # Synthesize TTS with unique turn hash to eliminate any browser caching or collision
        import uuid
        reply_audio_filename = f"sehat_reply_{session_id}_t{state.questions_asked_count}_{uuid.uuid4().hex[:6]}.wav"
        turn_audio_file = f"outputs/reports/{reply_audio_filename}"
        tts_res = self.tts.synthesize(bot_speech, output_path=turn_audio_file)
        reply_stream_url = f"/api/audio/stream/{reply_audio_filename}" if (os.path.exists(turn_audio_file) and os.path.getsize(turn_audio_file) > 500) else None

        # Always save updated realtime conversation turn to SQLite Consultation DB immediately
        try:
            from database.db_manager import GLOBAL_DB
            GLOBAL_DB.save_live_session(state)
        except Exception as e:
            logger.warning(f"Error saving realtime session {session_id} to DB: {e}")

        # If completed, generate clinical summary, update patient registry, and deliver to doctor queue
        if is_completed:
            summary_res = self.summary.generate(state)
            GLOBAL_PATIENT_REGISTRY.save_patient_visit(state)
            self.doctor.push_completed_summary(summary_res)
            GLOBAL_AUDIT_LOGGER.log_event(session_id, "SUMMARY_GENERATED", {"summary_id": session_id})
            try:
                from database.db_manager import GLOBAL_DB
                GLOBAL_DB.save_consultation(summary_res)
            except Exception:
                pass

        formatted_patient_transcript = dialogue_res.get("formatted_patient_transcript", final_transcript)

        return {
            "status": "success",
            "event": "SESSION_COMPLETED" if is_completed else "AI_RESPONSE",
            "session_id": session_id,
            "patient_transcript": formatted_patient_transcript,
            "raw_patient_transcript": final_transcript,
            "bot_speech_hi": bot_speech,
            "audio_url": reply_stream_url,
            "is_completed": is_completed,
            "state": state.to_dict(),
            "questions_asked_count": state.questions_asked_count,
            "total_budget": state.max_budget,
            "branch": state.branch
        }

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        state = GLOBAL_SESSION_STORE.get(session_id)
        if not state:
            return None
        if not state.generated_summary:
            summary_res = self.summary.generate(state)
            try:
                from database.db_manager import GLOBAL_DB
                GLOBAL_DB.save_consultation(summary_res)
            except Exception:
                pass
            return summary_res
        return state.generated_summary


# Global instance
GLOBAL_ORCHESTRATOR = SehatOrchestrator()
