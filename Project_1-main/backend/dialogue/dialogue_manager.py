import re
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from question_selector.question_selector import GLOBAL_QUESTION_SELECTOR, QuestionSelector
from urgency.urgency_engine import GLOBAL_URGENCY_ENGINE, UrgencyEngine
from session_store.session_store import SehatSessionState, GLOBAL_SESSION_STORE
from session_store.patient_registry import GLOBAL_PATIENT_REGISTRY, PatientRegistry
from audit.audit_logger import GLOBAL_AUDIT_LOGGER
from audio_pipeline.hinglish_formatter import format_patient_speech_hinglish

logger = logging.getLogger("sehat_dialogue")

NON_NAME_BLOCKED_WORDS = {
    # Shopping & Daily activities & Places
    "शॉपिंग", "shopping", "शाँपिंग", "शापिंग", "खरेदी", "खरेदीला", "मार्केट", "market", "बाजार", "मॉल", "mall",
    "दुकान", "shop", "ऑफिस", "office", "कामावर", "काम", "work", "job", "नोकरी", "घर", "घरी", "home", "house",
    "स्वयंपाक", "जेवण", "नाश्ता", "चहा", "tea", "breakfast", "lunch", "dinner", "व्यायाम", "जिम", "gym", "exercise",
    "चालणे", "walking", "प्रवास", "travel", "फिरणे", "फिरायला", "खेळणे", "गाडी", "बस", "ट्रेन", "रिक्षा", "शाळा", "school", "कॉलेज", "college",
    "बाहेर", "आत", "रस्ता", "गाव", "शहर",

    # Medical / Clinical / Symptoms / Diabetes terms
    "diabetes", "डायबिटीज", "डायबिटिज", "डायबीटीज", "डाएबेटिस", "डायाबीटीस", "मधुमेह", "sugar", "शुगर", "साखर",
    "insulin", "इन्सुलिन", "इंसुलिन", "metformin", "मेटफॉर्मिन", "bp", "बीपी", "blood", "रक्त", "pressure", "प्रेशर",
    "हॉस्पिटल", "hospital", "दवाखाना", "clinic", "डॉक्टर", "doctor", "वैद्य", "रिपोर्ट", "report", "टेस्ट", "test",
    "औषध", "औषधे", "गोळी", "गोळ्या", "medicine", "medicines", "tablet", "tablets", "चेकअप", "checkup", "तहान", "भूक",
    "लघवी", "यूरिन", "urine", "थकवा", "चक्कर", "दुखणे", "ताप", "fever", "खोकला", "cough", "सर्दी", "cold", "पोट",
    "डोके", "छाती", "हात", "पाय", "वजन", "weight", "लक्षण", "लक्षणे", "symptoms", "आजार", "रोग", "पेशंट", "patient", "रुग्ण",
    "इलाज", "उपचार", "ट्रीटमेंट", "treatment", "वेदना", "पेन", "pain", "प्रॉब्लेम", "problem", "इश्यू", "issue",

    # Greetings, Fillers, Interjections, Agreements & Disagreements
    "जी", "ji", "jee", "हाँ", "हां", "haan", "ha", "हो", "होय", "नाही", "नाहीये", "नाहित", "नाहीं", "yes", "no", "yeah", "yep", "nope", "nah", "ok", "okay",
    "ठीक", "अच्छा", "बरोबर", "कदाचित", "माहिती", "माहितीये", "माहित", "काही", "काहीतरी", "hello", "hi", "hey",
    "नमस्ते", "नमस्कार", "प्रणाम", "रामराम", "जय", "कृपया", "please", "thanks", "thank", "धन्यवाद", "थँक्यू",
    "चालेल", "बरं", "बर", "बरा", "नक्की", "हो नक्की", "सुरू", "शुरू", "करा", "करूया", "करू", "सांगा", "बोला", "पुढचे", "सांग",
    "वेलकम", "welcome", "बाय", "bye", "गुड", "good", "मॉर्निंग", "morning", "नाईट", "night",

    # Question words & Connectives
    "काय", "कसे", "कधी", "कुठे", "कोठे", "कोण", "केव्हा", "कशाला", "किती", "कसा", "कशी", "कसं", "कोणतं", "कोणती", "कोणता", "कोणत्या",
    "what", "why", "how", "when", "where", "who", "which", "whose", "whom",
    "आणि", "व", "किंवा", "पण", "परंतु", "म्हणून", "कारण", "जर", "तर", "मग", "सुद्धा", "देखील",
    "और", "या", "तथा", "एवं", "किंतु", "परंतु", "लेकिन", "मगर", "इसलिए", "क्योंकि", "तभी",
    "and", "or", "but", "so", "then", "because", "also", "too", "very", "much", "more", "some", "any", "all",

    # Verbs & Actions (Marathi / Hindi / English)
    "गेलो", "गेली", "गेले", "आलो", "आली", "आले", "जातो", "जाते", "जातात", "येतो", "येते", "येतात",
    "खातो", "खाते", "खातात", "खाल्ली", "खाल्ले", "पितो", "पिते", "पितात", "प्यायलो", "प्यायले",
    "बसलो", "बसले", "झोपलो", "झोपले", "उठलो", "उठले", "चाललो", "चालले", "करत", "करतो", "करते", "करतात",
    "केले", "केलं", "सांगतो", "सांगते", "सांगतात", "विचारतो", "विचारते", "बघतो", "बघते", "पाहतो", "पाहते",
    "ऐकतो", "ऐकते", "सांगा", "बोला", "विचारा", "विचारणे", "बोलणे", "सांगणे", "करणे", "खाणे", "पिणे", "झोपणे",
    "गया", "गयी", "गए", "आया", "आई", "आए", "जाता", "जाती", "जाते", "आता", "आती", "आते",
    "खाता", "खाती", "खाते", "पीता", "पीती", "पीते", "सोता", "उठता", "चलता", "करता", "करती", "करते",
    "कहा", "बोला", "सुना", "देखा", "बताओ", "पूछो", "बताइए", "बोलिए",

    # Pronouns & Particles
    "मी", "मैं", "मै", "मला", "तुला", "त्याला", "तिला", "आम्हाला", "तुम्हाला", "त्यांना",
    "माझा", "माझी", "माझे", "माझं", "माझ", "माझ्या", "तुझा", "तुझी", "तुझे", "तुझं", "तुझ",
    "त्याचा", "त्याची", "त्याचे", "त्याचं", "त्याचं", "तिचा", "तिची", "तिचे", "तिचं",
    "आमचा", "आमची", "आमचे", "आमचं", "तुमचा", "तुमची", "तुमचे", "तुमचं", "त्यांचा", "त्यांची", "त्यांचे", "त्यांचं",
    "आपला", "आपली", "आपले", "आपलं", "आपण", "तुम्ही", "आम्ही", "ते", "ती", "तो", "हे", "ही", "हा", "या", "याला", "यांचं", "स्वतः",
    "मुझे", "तुम्हें", "उसे", "उन्हें", "हमें", "आपको", "मेरा", "मेरी", "मेरे", "तुम्हारा", "तुम्हारी", "तुम्हारे", "उसका", "उसकी", "उसके",
    "हमारा", "हमारी", "हमारे", "आपका", "आपकी", "आपके", "अपना", "अपनी", "अपने", "कोई", "कुछ", "सब", "सभी",
    "है", "हैं", "हूँ", "हूं", "हुं", "हु", "हू", "आहे", "आहोत", "नाही", "होते", "होती", "होता", "होतो", "आहेत", "असेल", "असावे",
    "is", "am", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "i", "me", "my", "myself", "we", "our", "ours", "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "they", "them", "their",

    # Gender & Age & Details words
    "लिंग", "ling", "gender", "सेक्स", "sex", "पुरुष", "महिला", "स्त्री", "मर्द", "लड़का", "लड़की", "मुलगा", "मुलगी", "आदमी", "औरत",
    "male", "female", "man", "woman", "boy", "girl", "मेल", "फीमेल", "फिमेल", "जेंट्स", "gentleman", "पुरूष",
    "उम्र", "आयु", "वय", "age", "साल", "वर्ष", "वर्षे", "years", "yrs", "old", "saal", "varsh", "sal", "umra", "umar", "vay", "ayu",
    "नाव", "नाम", "name", "नेम", "माय", "details", "माहिती", "माहित", "profile", "user", "patient"
}

class DialogueManager:
    """
    Core Dialogue Manager for Sehat AI.
    Coordinates context-aware question selection, slot extraction, branch transitions,
    consent enforcement, follow-up patient recognition, and termination conditions.
    """
    def __init__(self, question_selector: Optional[QuestionSelector] = None, urgency_engine: Optional[UrgencyEngine] = None):
        self.selector = question_selector or GLOBAL_QUESTION_SELECTOR
        self.urgency_engine = urgency_engine or GLOBAL_URGENCY_ENGINE

    def start_session(self, session_id: Optional[str] = None) -> Tuple[SehatSessionState, str]:
        """Initialize new Sehat AI pre-screening session with mandatory Sehat greeting."""
        sid = session_id or f"sehat_{uuid.uuid4().hex[:8]}"
        state = GLOBAL_SESSION_STORE.get_or_create(sid)
        state.current_question_id = "COM_CONSENT"
        state.asked_question_ids = ["COM_CONSENT"]
        state.questions_asked_count = 1

        first_prompt = (
            "नमस्ते, मेरा नाम Diabetes Dost है। मैं Doctor से मिलने से पहले आपकी Diabetes से जुड़ी कुछ Health "
            "जानकारी समझने में help करूंगा। क्या आप बातचीत और Audio Recording के लिए सहमत हैं?"
        )

        GLOBAL_AUDIT_LOGGER.log_event(sid, "SESSION_STARTED", {"initial_question_id": "COM_CONSENT"})
        GLOBAL_SESSION_STORE.save(state)
        return state, first_prompt

    def start_followup_session(self, patient_name_or_id: str, session_id: Optional[str] = None) -> Tuple[SehatSessionState, str]:
        """Initialize a follow-up consultation for a returning registered patient."""
        sid = session_id or f"sehat_fu_{uuid.uuid4().hex[:8]}"
        state = GLOBAL_SESSION_STORE.get_or_create(sid)

        # Look up existing patient record
        patient_record = GLOBAL_PATIENT_REGISTRY.find_patient(patient_name_or_id)
        if patient_record:
            p_name = patient_record.get("name", patient_name_or_id)
            p_age = patient_record.get("age")
            p_gender = patient_record.get("gender")
            d_type = patient_record.get("diabetes_type")
            meds = patient_record.get("active_medications", [])
            last_sugar = patient_record.get("last_blood_sugar")

            state.demographics = {"name": p_name, "age": p_age, "gender": p_gender}
            state.consent = True
            state.audio_recording_consent = True
            state.branch = "follow_up"
            state.diabetes_type = d_type
            state.diabetes_history = patient_record.get("baseline_diabetes_duration")
            state.family_history = patient_record.get("family_history")
            state.medications = list(meds)
            state.completed_topics = ["consent", "demographics", "diabetic_status"]
            state.volunteered_slots = ["consent", "demographics", "diabetic_status"]
            state.current_question_id = "FU_RECENT_SUGAR"
            state.asked_question_ids = ["FU_RECENT_SUGAR"]
            state.questions_asked_count = 1
            state.max_budget = 8

            state.context_memory = {
                "is_follow_up": True,
                "patient_name": p_name,
                "prev_sugar": last_sugar,
                "prev_meds": meds,
                "diabetes_type": d_type,
                "total_visits": patient_record.get("total_visits_count", 1)
            }

            meds_text = f"आपकी निर्धारित दवाएं ({', '.join(meds)})" if meds else "आपकी दवाएं"
            sugar_text = f" और पिछली बार आपकी Blood Sugar {last_sugar} mg/dL दर्ज थी" if last_sugar else ""

            followup_greeting = (
                f"नमस्ते {p_name} जी, Deenanath Mangeshkar Hospital के Diabetes Dost में आपका दोबारा स्वागत है। "
                f"हमारे रिकॉर्ड के अनुसार {meds_text}{sugar_text}। आइए आज का आपका Regular Follow-up Check-up शुरू करते हैं। "
                f"पिछले परामर्श के बाद क्या आपने हाल ही में अपनी Fasting या PP Blood Sugar टेस्ट कराई है? यदि याद हो तो आपकी Sugar कितनी आई थी?"
            )
        else:
            p_name = patient_name_or_id
            state.demographics["name"] = p_name
            state.consent = True
            state.audio_recording_consent = True
            state.branch = "follow_up"
            state.current_question_id = "FU_RECENT_SUGAR"
            state.asked_question_ids = ["FU_RECENT_SUGAR"]
            state.questions_asked_count = 1
            state.max_budget = 8
            followup_greeting = (
                f"नमस्ते {p_name} जी, Diabetes Dost में आपका दोबारा स्वागत है। "
                f"आइए आज का आपका Regular Follow-up Check-up शुरू करते हैं। "
                f"पिछले परामर्श के बाद क्या आपने हाल ही में अपनी Fasting या PP Blood Sugar टेस्ट कराई है? यदि याद हो तो आपकी Sugar कितनी आई थी?"
            )

        GLOBAL_AUDIT_LOGGER.log_event(sid, "FOLLOWUP_SESSION_STARTED", {"patient_name": p_name, "initial_question_id": "FU_RECENT_SUGAR"})
        GLOBAL_SESSION_STORE.save(state)
        return state, followup_greeting

    def process_turn(self, session_id: str, patient_utterance: str) -> Dict[str, Any]:
        """
        Process a patient's voice turn.
        Extracts clinical entities, determines consent / branch, evaluates risk signals,
        acknowledges the patient's specific reply empathetically, and selects the next context-aware question.
        Only at the end after listening to all turns does it deliver the comprehensive clinical opinion.
        """
        state = GLOBAL_SESSION_STORE.get_or_create(session_id)
        current_qid = state.current_question_id

        # 0. Check for inaudible / unclear / empty response (Retry once safeguard)
        clean_text = (patient_utterance or "").strip()
        is_inaudible = (
            len(clean_text) < 2 or
            clean_text in ["...", "हम्म", "hmm", "uh", "um", "क्या", "?", "voice"]
        )
        if is_inaudible and current_qid != "COMPLETED":
            retries = state.question_retry_count.get(current_qid, 0)
            if retries < 1:
                state.question_retry_count[current_qid] = retries + 1
                q_text = self._lookup_question_text(current_qid)
                retry_speech = f"माफ कीजिए, आपकी Voice स्पष्ट नहीं आई। {q_text}"
                GLOBAL_AUDIT_LOGGER.log_event(session_id, "QUESTION_RETRY", {
                    "question_id": current_qid,
                    "reason": "inaudible_response"
                })
                GLOBAL_SESSION_STORE.save(state)
                return {
                    "bot_speech_hi": retry_speech,
                    "is_completed": False,
                    "state": state.to_dict(),
                    "next_question_id": current_qid,
                    "questions_asked_count": state.questions_asked_count,
                    "max_budget": state.max_budget
                }

        # 1. Format Patient Input (English words in English script, Hindi words in Hindi Devanagari)
        formatted_utterance = format_patient_speech_hinglish(patient_utterance)

        state.record_answer(
            question_id=current_qid,
            question_hi=self._lookup_question_text(current_qid),
            patient_answer_hi=formatted_utterance
        )
        GLOBAL_AUDIT_LOGGER.log_event(session_id, "PATIENT_RESPONSE", {
            "question_id": current_qid,
            "patient_utterance": formatted_utterance,
            "raw_utterance": patient_utterance
        })

        # 2. Process Q1: Mandatory Consent Check
        if current_qid == "COM_CONSENT":
            res = self._handle_consent_turn(state, formatted_utterance)
            res["formatted_patient_transcript"] = formatted_utterance
            return res

        # 3. Process Q2: Demographics Extraction & Mandatory Completeness Check
        if current_qid == "COM_DEMOGRAPHICS":
            self._extract_demographics(state, formatted_utterance)
            
            missing_fields = []
            if not state.demographics.get("name"):
                missing_fields.append("Name")
            if not state.demographics.get("age"):
                missing_fields.append("Age")
            if not state.demographics.get("gender"):
                missing_fields.append("Gender")

            if missing_fields and state.demographic_retry_count < 2:
                state.demographic_retry_count += 1
                p_name = state.demographics.get("name", "")
                
                if len(missing_fields) == 1:
                    field = missing_fields[0]
                    if "Gender" in field:
                        bot_speech = f"धन्यवाद {p_name} जी, कृपया अपना Gender भी बताइए।" if p_name else "धन्यवाद, कृपया अपना Gender भी बताइए।"
                    elif "Age" in field:
                        bot_speech = f"धन्यवाद {p_name} जी, कृपया अपनी Age भी बताइए।" if p_name else "धन्यवाद, कृपया अपनी Age भी बताइए।"
                    else:
                        bot_speech = "धन्यवाद, कृपया अपना पूरा Name भी बताइए।"
                else:
                    bot_speech = f"धन्यवाद, कृपया अपना {' और '.join(missing_fields)} भी स्पष्ट रूप से बताइए।"

                GLOBAL_AUDIT_LOGGER.log_event(session_id, "DEMOGRAPHIC_INCOMPLETE_RETRY", {
                    "missing_fields": missing_fields,
                    "retry_count": state.demographic_retry_count
                })
                GLOBAL_SESSION_STORE.save(state)
                return {
                    "bot_speech_hi": bot_speech,
                    "formatted_patient_transcript": formatted_utterance,
                    "is_completed": False,
                    "state": state.to_dict(),
                    "next_question_id": "COM_DEMOGRAPHICS",
                    "questions_asked_count": state.questions_asked_count,
                    "max_budget": state.max_budget
                }

            if "demographics" not in state.completed_topics:
                state.completed_topics.append("demographics")

        # 4. Mid-session branch re-alignment or Q3 branch selection
        u_lower = formatted_utterance.lower()
        if any(w in u_lower for w in ["मुझे डायबिटीज नहीं है", "मुझे शुगर नहीं है", "डायबिटीज ही नहीं है", "no diabetes", "nahi hai diabetes", "diabetes nahi hai", "diabetes nahi", "not diabetic"]):
            if state.branch != "not_diabetic":
                state.branch = "not_diabetic"
                if "diabetic_status" not in state.completed_topics:
                    state.completed_topics.append("diabetic_status")
        elif current_qid == "COM_STATUS":
            is_recognized = self._determine_branch(state, formatted_utterance)
            if not is_recognized:
                # Ambiguous / Incomplete / Garbled input (e.g. "मुझे डायल।") -> re-ask clearly before advancing
                retries = getattr(state, "status_retry_count", 0)
                if retries < 2:
                    state.status_retry_count = retries + 1
                    clarify_speech = (
                        "माफ कीजिए, आपकी बात पूरी तरह स्पष्ट नहीं हो पाई। "
                        "कृपया साफ बताइए कि क्या आपको पहले से Diabetes (Sugar) की बीमारी है, "
                        "या आपको Diabetes नहीं है, या आपको इसके कोई Symptoms (लक्षण) महसूस हो रहे हैं?"
                    )
                    GLOBAL_AUDIT_LOGGER.log_event(session_id, "STATUS_INCOMPLETE_RETRY", {
                        "raw_utterance": patient_utterance,
                        "retry_count": state.status_retry_count
                    })
                    GLOBAL_SESSION_STORE.save(state)
                    return {
                        "bot_speech_hi": clarify_speech,
                        "formatted_patient_transcript": formatted_utterance,
                        "is_completed": False,
                        "state": state.to_dict(),
                        "next_question_id": "COM_STATUS",
                        "questions_asked_count": state.questions_asked_count,
                        "max_budget": state.max_budget
                    }
                else:
                    state.branch = "unsure"

            if "diabetic_status" not in state.completed_topics:
                state.completed_topics.append("diabetic_status")

        # 5. Extract Clinical Entities & Symptoms from formatted English+Hindi context
        self._extract_clinical_slots(state, formatted_utterance)

        # 6. Check for Closing Question Response (Normal Completion with Complete Clinical Opinion)
        if current_qid == "CLS_FINAL_FEEDBACK" or (state.current_question_id and state.current_question_id.startswith("CLS_")):
            state.is_completed = True
            self._finalize_urgency(state)
            closing_speech = self._build_final_opinion_speech(state)
            GLOBAL_AUDIT_LOGGER.log_event(session_id, "SESSION_COMPLETED", {"status": "normal_completion"})
            GLOBAL_SESSION_STORE.save(state)
            return {
                "bot_speech_hi": closing_speech,
                "formatted_patient_transcript": formatted_utterance,
                "is_completed": True,
                "state": state.to_dict(),
                "next_question_id": "COMPLETED",
                "questions_asked_count": state.questions_asked_count,
                "max_budget": state.max_budget
            }

        # 7. Select Context-Aware Next Question based on what the user said
        next_q = self.selector.select_next_question(
            current_branch=state.branch,
            asked_question_ids=state.asked_question_ids,
            completed_topics=state.completed_topics,
            questions_asked_count=state.questions_asked_count,
            demographics=state.demographics,
            symptoms_reported=state.symptoms_reported,
            risk_signals=state.risk_signals,
            max_budget=state.max_budget,
            context_memory=state.context_memory,
            sugar_readings=state.blood_sugar_readings,
            medications=state.medications,
            symptoms_denied=state.symptoms_denied,
            volunteered_slots=state.volunteered_slots
        )

        if not next_q:
            # Reached natural conclusion -> Provide full clinical opinion & summary
            state.is_completed = True
            self._finalize_urgency(state)
            closing_speech = self._build_final_opinion_speech(state)
            GLOBAL_AUDIT_LOGGER.log_event(session_id, "SESSION_COMPLETED", {"status": "questions_exhausted"})
            GLOBAL_SESSION_STORE.save(state)
            return {
                "bot_speech_hi": closing_speech,
                "formatted_patient_transcript": formatted_utterance,
                "is_completed": True,
                "state": state.to_dict(),
                "next_question_id": "COMPLETED",
                "questions_asked_count": state.questions_asked_count,
                "max_budget": state.max_budget
            }

        # Advance Question State
        state.questions_asked_count += 1
        state.current_question_id = next_q["question_id"]
        state.asked_question_ids.append(next_q["question_id"])
        if next_q.get("topic") and next_q["topic"] not in state.completed_topics:
            state.completed_topics.append(next_q["topic"])

        # Frame next question with empathetic acknowledgment based on previous answer
        bot_speech = self._frame_next_question(state, current_qid, formatted_utterance, next_q)

        GLOBAL_AUDIT_LOGGER.log_event(session_id, "QUESTION_SELECTED", {
            "question_id": next_q["question_id"],
            "question_text": bot_speech,
            "turn_number": state.questions_asked_count
        })

        self._finalize_urgency(state)
        GLOBAL_SESSION_STORE.save(state)

        return {
            "bot_speech_hi": bot_speech,
            "formatted_patient_transcript": formatted_utterance,
            "is_completed": False,
            "state": state.to_dict(),
            "next_question_id": next_q["question_id"],
            "questions_asked_count": state.questions_asked_count,
            "max_budget": state.max_budget
        }

    def _frame_next_question(self, state: SehatSessionState, prev_qid: str, patient_utterance: str, next_q: Dict[str, Any]) -> str:
        """
        Dynamically builds a personalized conversational bridge directly acknowledging
        what the user said in the previous turn using Context Memory.
        Never repeats the patient's name repeatedly on every turn.
        """
        p_name = state.demographics.get("name")
        next_raw_q = next_q.get("question_hi", "")
        u_lower = patient_utterance.lower()

        # 1. Patient reaffirmed they do not have diabetes
        if any(w in u_lower for w in ["डायबिटीज नहीं है", "शुगर नहीं है", "डायबिटीज ही नहीं है", "no diabetes", "nahi hai diabetes"]):
            return f"बिल्कुल, समझ गया कि आपको Diabetes नहीं है। {next_raw_q}"

        # 2. Acknowledgment after Demographics (Turn 2 -> 3 ONLY: use name once here)
        if prev_qid == "COM_DEMOGRAPHICS":
            if p_name:
                return f"धन्यवाद {p_name} जी, आपकी Details नोट कर ली गई हैं। {next_raw_q}"
            return f"धन्यवाद, आपकी Details नोट कर ली गई हैं। {next_raw_q}"

        # 3. Acknowledgment after Diabetic Status / Type
        if prev_qid == "COM_STATUS":
            if state.branch == "known_diabetic":
                return f"जी, समझ गया। {next_raw_q}"
            elif state.branch == "not_diabetic":
                cleaned_next_q = re.sub(r"^(?:यह अच्छी बात है[।,\.\s]*)+", "", next_raw_q).strip()
                return f"यह अच्छी बात है कि आपको Diabetes नहीं है। {cleaned_next_q}"
            else:
                return f"जी ठीक है, आइए आपकी Health और Symptoms को समझ लेते हैं। {next_raw_q}"

        if prev_qid == "KD_DIABETES_TYPE":
            if getattr(state, "diabetes_type", None):
                return f"जी, आपका {state.diabetes_type} का Record नोट कर लिया गया है। {next_raw_q}"
            return f"जी ठीक है। {next_raw_q}"

        # 4. Acknowledgment for Medications / Insulin (Turn for medications ONLY)
        if prev_qid == "KD_MEDICATIONS":
            if any(w in u_lower for w in ["नहीं", "nahin", "no", "nahi leta", "नहीं लेता", "नहीं लेती", "कोई नहीं"]):
                return f"समझ गया, आप कोई Medicine नहीं ले रहे हैं। {next_raw_q}"
            elif "इंसुलिन" in u_lower or "insulin" in u_lower:
                return f"ठीक है, Insulin लेने का Record नोट कर लिया गया है। {next_raw_q}"
            else:
                return f"ठीक है, आपकी Regular Medicines का Record नोट कर लिया गया है। {next_raw_q}"

        # 5. Acknowledgment for Blood Sugar Values with Context Memory
        if prev_qid in ["KD_SUGAR_LEVELS", "UN_PREV_TESTING", "ND_RECENT_SCREENING"]:
            recent_reading = state.blood_sugar_readings[-1]["value"] if state.blood_sugar_readings else None
            if recent_reading:
                if recent_reading >= 250:
                    return f"जी, आपका {recent_reading} mg/dL का Blood Sugar Level काफी High (Elevated) है। {next_raw_q}"
                elif recent_reading < 70:
                    return f"जी, आपका {recent_reading} mg/dL का Blood Sugar Level Low Sugar (Hypoglycemia) दिखाता है। {next_raw_q}"
                else:
                    return f"जी, आपका {recent_reading} mg/dL का Blood Sugar Level नोट कर लिया गया है। {next_raw_q}"
            elif any(w in u_lower for w in ["नहीं", "nahin", "no", "याद नहीं"]):
                return f"कोई बात नहीं। {next_raw_q}"
            else:
                return f"जी ठीक है। {next_raw_q}"

        # 6. Acknowledgment for Symptoms with Context Memory
        if "all_symptoms" in state.symptoms_denied or any(w in u_lower for w in ["कोई लक्षण नहीं", "कोई समस्या नहीं", "no symptoms", "fine", "kuch nahi"]):
            return f"यह अच्छी बात है कि आपको कोई Severe Symptoms नहीं हैं। {next_raw_q}"

        if prev_qid in ["KD_THIRST_URINATION", "UN_CLASSIC_SYMPTOMS"]:
            if any(w in u_lower for w in ["प्यास", "पेशाब", "thirst", "urine", "हाँ", "हां", "yes", "होती है", "लगती है"]):
                return f"जी, Excessive Thirst और Frequent Urination की जानकारी नोट कर ली गई है। {next_raw_q}"
            return f"जी धन्यवाद, यह जानकारी नोट कर ली गई है। {next_raw_q}"

        if prev_qid in ["KD_VISION_FATIGUE", "UN_ENERGY_VISION"]:
            if any(w in u_lower for w in ["थकान", "धुंधला", "कमजोरी", "fatigue", "vision", "blur", "हाँ", "हां", "yes"]):
                return f"जी, थकान और नजर से जुड़ी Details नोट कर ली गई हैं। {next_raw_q}"
            return f"जी, समझ गया। {next_raw_q}"

        if prev_qid in ["KD_NUMBNESS_WOUNDS", "UN_HEALING_NUMBNESS"]:
            if any(w in u_lower for w in ["घाव", "सुन्न", "झनझनाहट", "wound", "numb", "tingling", "हाँ", "हां", "yes", "जलन"]):
                return f"जी, हाथ-पैरों में Numbness (सुन्नपन) व झनझनाहट की बात नोट कर ली गई है। {next_raw_q}"
            return f"जी, यह नोट कर लिया गया है। {next_raw_q}"

        if prev_qid in ["KD_HYPO_EPISODES"]:
            if any(w in u_lower for w in ["हाँ", "हां", "yes", "पसीना", "कांप", "sweat", "shivering"]):
                return f"जी, Low Sugar (Hypoglycemia) के लक्षणों की जानकारी नोट कर ली गई है। {next_raw_q}"
            return f"जी धन्यवाद। {next_raw_q}"

        if prev_qid in ["KD_LIFESTYLE_DIET", "ND_PHYSICAL_ACTIVITY", "ND_WEIGHT_LIFESTYLE"]:
            return f"जी, Lifestyle और Daily Activity की जानकारी नोट कर ली गई है। {next_raw_q}"

        # 7. Acknowledgment for Family History
        if prev_qid in ["UN_FAMILY_HISTORY", "ND_FAMILY_HISTORY", "KD_FAMILY_HISTORY"] or (prev_qid and "family" in prev_qid.lower()):
            if state.family_history is True:
                return f"जी, परिवार में Diabetes का इतिहास नोट कर लिया गया है। {next_raw_q}"
            elif state.family_history is False:
                return f"जी, समझ गया, परिवार में Diabetes की History नहीं है। {next_raw_q}"
            return f"जी, Family History नोट कर ली गई है। {next_raw_q}"

        # 8. Acknowledgment for Pregnancy History
        if prev_qid in ["UN_PREGNANCY_HISTORY", "ND_PREGNANCY_HISTORY", "KD_PREGNANCY_HISTORY"] or (prev_qid and "pregnancy" in prev_qid.lower()):
            if state.pregnancy_history is True:
                return f"जी, आपकी Pregnancy History नोट कर ली गई है। {next_raw_q}"
            elif state.pregnancy_history is False:
                return f"जी ठीक है, Pregnancy History में कोई पूर्व समस्या दर्ज नहीं है। {next_raw_q}"
            return f"जी धन्यवाद। {next_raw_q}"

        # Follow-up Specific Question Acknowledgments
        if prev_qid == "FU_RECENT_SUGAR":
            recent_reading = state.blood_sugar_readings[-1]["value"] if state.blood_sugar_readings else None
            if recent_reading:
                if recent_reading >= 250:
                    return f"जी, आपका {recent_reading} mg/dL का Sugar Level काफी High (Elevated) है। {next_raw_q}"
                elif recent_reading < 70:
                    return f"जी, आपका {recent_reading} mg/dL का Sugar Level Low Sugar (Hypoglycemia) दर्शाता है। {next_raw_q}"
                else:
                    return f"जी, आपका {recent_reading} mg/dL का हालिया Blood Sugar Level नोट कर लिया गया है। {next_raw_q}"
            return f"जी धन्यवाद। {next_raw_q}"

        if prev_qid == "FU_MED_COMPLIANCE":
            return f"जी, आपकी दवाओं के सेवन का रिकॉर्ड नोट कर लिया गया है। {next_raw_q}"

        if prev_qid == "FU_SYMPTOM_PROGRESSION":
            return f"जी, लक्षणों में बदलाव की स्थिति दर्ज कर ली गई है। {next_raw_q}"

        if prev_qid == "FU_HYPO_EPISODES":
            return f"जी, यह जानकारी नोट कर ली गई है। {next_raw_q}"

        if prev_qid == "FU_LIFESTYLE_UPDATE":
            return f"जी, Lifestyle Details नोट कर ली गई हैं। {next_raw_q}"

        # 9. General fallback: Do NOT repeat old acknowledgements or patient name
        return f"{next_raw_q}"

    def _build_final_opinion_speech(self, state: SehatSessionState) -> str:
        """
        Builds a comprehensive, personalized clinical opinion and triage recommendation
        only after listening fully to the user's entire consultation.
        """
        p_name = state.demographics.get("name")
        greeting_prefix = f"{p_name} जी, " if p_name else ""
        
        # Clinical synthesis components
        findings = []
        if state.branch == "known_diabetic":
            if getattr(state, "diabetes_type", None):
                findings.append(f"आपको {state.diabetes_type} Diabetes है")
            else:
                findings.append("आपको पहले से Diabetes है")
        elif state.branch == "unsure" and state.symptoms_reported:
            findings.append("आपमें Diabetes से मिलते-जुलते Symptoms देखे गए हैं")
        elif state.branch == "not_diabetic":
            findings.append("आपको पहले से Diabetes नहीं है")

        if state.family_history is True:
            findings.append("Family में Diabetes की Positive History है")
        elif state.family_history is False:
            findings.append("Family में Diabetes की कोई History नहीं है")

        if state.pregnancy_history is True:
            if state.gestational_history is True:
                findings.append("Pregnancy के दौरान Gestational Diabetes (GDM) की History रही है")
            elif state.gestational_history is False:
                findings.append("Pregnancy के दौरान Sugar सामान्य (Normal) रही है")
            else:
                findings.append("Pregnancy की History दर्ज है")

        if state.symptoms_reported:
            sym_names = []
            if "polydipsia_excessive_thirst" in state.symptoms_reported:
                sym_names.append("Excessive Thirst (प्यास)")
            if "polyuria_frequent_urination" in state.symptoms_reported:
                sym_names.append("Frequent Urine (पेशाब)")
            if "fatigue_weakness" in state.symptoms_reported:
                sym_names.append("Fatigue (थकान)")
            if "blurred_vision" in state.symptoms_reported:
                sym_names.append("Blurry Vision")
            if "delayed_wound_healing" in state.symptoms_reported:
                sym_names.append("Delayed Wound Healing (घाव भरने में देरी)")
            if "numbness_tingling" in state.symptoms_reported:
                sym_names.append("Numbness (हाथ-पैरों में सुन्नपन)")
            if sym_names:
                findings.append(f"आपके बताए मुख्य Symptoms ({', '.join(sym_names)}) हैं")

        if state.blood_sugar_readings:
            recent_sugar = state.blood_sugar_readings[-1]["value"]
            findings.append(f"हालिया Blood Sugar Level लगभग {recent_sugar} mg/dL दर्ज है")

        findings_summary = " और ".join(findings) if findings else "आपकी Health Details नोट कर ली गई हैं"

        # Triage and advice synthesis
        advice = (
            "Diabetes के proper management के लिए Regular Blood Sugar Test (Fasting व PP) और हर 3 months में HbA1c Test कराना जरूरी है। "
            "Healthy Diet रखें और पर्याप्त पानी पिएं।"
        )

        closing_opinion = (
            f"धन्यवाद। {greeting_prefix}मैंने आपकी पूरी बात ध्यानपूर्वक सुन ली है। {findings_summary}। "
            f"{advice} Doctor के लिए आपकी संपूर्ण Clinical Summary (Deenanath Mangeshkar Hospital Triage Report) तैयार कर दी गई है। "
            f"कृपया यहाँ Deenanath Mangeshkar Hospital में प्रतीक्षा करें, Doctor जल्द ही आपसे Consult करेंगे।"
        )
        return closing_opinion

    def _handle_consent_turn(self, state: SehatSessionState, utterance: str) -> Dict[str, Any]:
        cleaned = utterance.lower()
        
        # 1. Explicit Rejection patterns (including negated agreement)
        rejection_patterns = [
            r"\b(disagree|don\'?t\s*agree|do\s*not\s*agree|not\s*agree|no\s*agree|reject|no|nahin|nahi|asahmat|mana|deny|cancel|stop|don\'?t\s*consent)\b",
            r"(नहीं|ना|डिसअग्री|सहमति\s*नहीं|सहमत\s*नहीं|असहमत|मना|रिकॉर्ड\s*मत\s*करो|अनुमति\s*नहीं)"
        ]
        is_rejection = any(re.search(pat, cleaned, re.IGNORECASE) for pat in rejection_patterns)
        
        # 2. Check affirmative override
        has_affirmative_override = (
            any(w in cleaned for w in ["हाँ", "हां", "yes", "bilkul", "बिल्कुल", "sure", "ok", "okay"]) and
            not any(re.search(p, cleaned) for p in [r"सहमत\s*नहीं", r"not\s*agree", r"don\'?t\s*agree", r"सहमति\s*नहीं", r"disagree", r"डिसअग्री"])
        )

        if is_rejection and not has_affirmative_override:
            state.consent = False
            state.consent_rejected = True
            state.is_completed = True
            exit_speech = "समझ गया। आपकी Consent के बिना हम यह Pre-Screening आगे नहीं बढ़ाएंगे। आपका धन्यवाद।"
            GLOBAL_AUDIT_LOGGER.log_event(state.session_id, "CONSENT_REJECTED", {"utterance": utterance})
            GLOBAL_SESSION_STORE.save(state)
            return {
                "bot_speech_hi": exit_speech,
                "is_completed": True,
                "consent_rejected": True,
                "state": state.to_dict(),
                "next_question_id": "CONSENT_REJECTED"
            }

        state.consent = True
        state.audio_recording_consent = True
        state.consent_timestamp = datetime.now(timezone.utc).isoformat()
        state.questions_asked_count += 1
        state.current_question_id = "COM_DEMOGRAPHICS"
        state.asked_question_ids.append("COM_DEMOGRAPHICS")
        if "consent" not in state.completed_topics:
            state.completed_topics.append("consent")

        q2_speech = "धन्यवाद। आपकी सही पहचान और Record के लिए, कृपया अपना पूरा Name, Age और Gender बताइए।"
        GLOBAL_AUDIT_LOGGER.log_event(state.session_id, "CONSENT_GRANTED", {"timestamp": state.consent_timestamp})
        GLOBAL_SESSION_STORE.save(state)

        return {
            "bot_speech_hi": q2_speech,
            "is_completed": False,
            "state": state.to_dict(),
            "next_question_id": "COM_DEMOGRAPHICS",
            "questions_asked_count": state.questions_asked_count,
            "max_budget": state.max_budget
        }

    def _determine_branch(self, state: SehatSessionState, utterance: str) -> bool:
        """
        Determines the patient's diabetic status branch:
        - not_diabetic: explicitly states no diabetes / normal
        - unsure: unsure or suspecting symptoms or requesting checkup
        - known_diabetic: diagnosed diabetic / taking medications / type 1 / type 2
        Returns True if a clear status is recognized.
        Returns False if the utterance is ambiguous / truncated (e.g. 'मुझे डायल', 'डायल', etc.)
        """
        cleaned = utterance.lower().strip()

        # 1. Explicit Negation (NOT Diabetic)
        negations = [
            "नहीं है", "नहीं", "नही", "ना", "डायबिटीज नहीं", "शुगर नहीं", "nahi hai", "nahin", "nahi", "na",
            "no diabetes", "no", "not diabetic", "normal", "नॉर्मल", "kuch nahi", "कुछ नहीं", "नेगेटिव", "negative",
            "i don't have diabetes", "i dont have diabetes", "i do not have diabetes", "no sugar", "non diabetic",
            "never had diabetes", "healthy", "don't have sugar", "dont have sugar", "no sugar problem",
            "नाही", "नाहीये", "डायबिटीज नाही", "शुगर नाही", "काही नाही", "नाही मला", "नॉर्मल आहे", "शुगर नाही मला"
        ]
        if any(w in cleaned for w in negations):
            state.branch = "not_diabetic"
            state.diabetes_history = None
            state.diabetes_type = None
            return True

        # 2. Known Diabetic Positive Indicators
        positive_words = [
            "डायबिटीज है", "शुगर है", "हाँ", "हां", "yes", "diabetic", "diabetes", "डायबिटीज", "डायबीटीज", "डायबिटिज",
            "डायबिटीस", "डायबटीज", "शुगर", "sugar", "sugar hai", "type 2", "type 1", "टाइप 2", "टाइप 1", "yes i have",
            "haan", "ha", "पहले से है", "साल से", "महीने से", "i have diabetes", "i have sugar", "diagnosed with diabetes",
            "i am diabetic", "i take insulin", "i take metformin", "suffering from diabetes", "taking medicines",
            "इन्सुलिन", "इंसुलिन", "insulin", "गोळ्या चालू", "दवा चालू", "दवाई लेता", "दवाई लेती", "होय", "आहे",
            "डायबिटीज आहे", "शुगर आहे", "आहे मला"
        ]
        if any(w in cleaned for w in positive_words):
            state.branch = "known_diabetic"
            return True

        # 3. Check Unsure / Symptoms / Suspecting / Screening
        unsure_words = [
            "पता नहीं", "शायद", "मालूम नहीं", "unsure", "not sure", "laksahn", "लक्षण", "doubt", "हो सकता",
            "symptoms", "doubtful", "borderline", "चेक कराना है", "check karana hai", "maybe", "i think so",
            "i don't know", "i dont know", "suspecting", "possible", "not tested",
            "माहित नाही", "माहीत नाही", "कदाचित", "लक्षणे", "लक्षणे आहेत", "तपासणी करायची आहे", "शंका आहे", "चेक करायचे आहे"
        ]
        if any(w in cleaned for w in unsure_words):
            state.branch = "unsure"
            state.diabetes_history = None
            state.diabetes_type = None
            return True

        # 4. Incomplete / Ambiguous / Truncated inputs (e.g. 'मुझे डायल', 'डायल', 'हूँ', etc.)
        return False

    def _is_valid_name_token(self, raw_tok: str) -> bool:
        if not raw_tok:
            return False
        tok = raw_tok.strip("।,;:.?!()\"'॥\u0964\u0965 \t\n\r-_/\\").lower()
        if len(tok) < 2 or tok.isdigit():
            return False
        if tok in NON_NAME_BLOCKED_WORDS:
            return False
        # Strip Marathi/Hindi postpositions and case endings (e.g. शॉपिंगला, कामावर, बाजारात, घरात, डॉक्टरकडे, सालकी)
        suffixes = [
            "ला", "ना", "वर", "कडे", "हून", "मध्ये", "साठी", "पर्यंत", "सारखे", "बद्दल", "बाबत",
            "चा", "ची", "चे", "च्या", "त", "ने", "नी", "शी", "तील", "तून", "वरून", "पासून", "बाबत",
            "का", "की", "के", "सा", "सी", "से", "चा", "ची"
        ]
        if any(tok.startswith(prefix) for prefix in ["साल", "वर्ष", "वय", "उम्र", "year"]):
            return False
        for suf in suffixes:
            if tok.endswith(suf) and len(tok) > len(suf) + 1:
                stem = tok[:-len(suf)]
                if stem in NON_NAME_BLOCKED_WORDS or any(stem.startswith(prefix) for prefix in ["साल", "वर्ष", "वय", "उम्र"]):
                    return False
        return True

    def _is_valid_patient_name(self, candidate: str) -> bool:
        if not candidate or not isinstance(candidate, str):
            return False
        cleaned = re.sub(r"[।,;:\.\?!()\"'/\-_।॥\u0964\u0965]", " ", candidate).strip()
        tokens = cleaned.split()
        if not tokens or len(tokens) > 3:
            return False
        for t in tokens:
            if not self._is_valid_name_token(t):
                return False
        return True

    def _extract_demographics(self, state: SehatSessionState, utterance: str):
        u_lower = utterance.lower()

        # 1. Age extraction (Digits + Marathi/Hindi words + English words)
        age_val = None
        
        # Check direct integer match with optional age/years prefix or suffix
        age_match = re.search(r"\b(?:age|age\s*is|aged|i\s*am|i\'?m|उम्र|आयु|वय)?\s*(\d{1,3})\s*(?:वर्ष|साल|years?|saal|yr|yrs|sal|old|वर्षे|varsh)?\b", utterance, re.IGNORECASE)
        if age_match:
            try:
                v = int(age_match.group(1))
                if 1 <= v <= 120:
                    age_val = v
            except ValueError:
                pass

        if not age_val:
            word_num_map = {
                "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाच": 5, "छह": 6, "सहा": 6, "सात": 7, "आठ": 8, "नौ": 9, "नऊ": 9, "दस": 10, "दहा": 10,
                "ग्यारह": 11, "अकरा": 11, "बारह": 12, "बारा": 12, "तेरह": 13, "तेरा": 13, "चौदह": 14, "चौदा": 14, "पंद्रह": 15, "पंधरा": 15,
                "सोलह": 16, "सोळा": 16, "सत्रह": 17, "सतरा": 17, "अट्ठारह": 18, "अठरा": 18, "उन्नीस": 19, "एकोणीस": 19, "बीस": 20, "वीस": 20,
                "इक्कीस": 21, "एकवीस": 21, "बाईस": 22, "बावीस": 22, "तेईस": 23, "तेवीस": 23, "चौबीस": 24, "चोवीस": 24, "पच्चीस": 25, "पंचवीस": 25,
                "छब्बीस": 26, "सव्वीस": 26, "सत्ताईस": 27, "सत्तावीस": 27, "अट्ठाईस": 28, "अठ्ठावीस": 28, "उनतीस": 29, "एकोणतीस": 29, "तीस": 30,
                "इकतीस": 31, "बत्तीस": 32, "तैंतीस": 33, "चौंतीस": 34, "पैंतीस": 35, "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38, "उनतालीस": 39, "चालीस": 40,
                "इकतालीस": 41, "बयालीस": 42, "तैंतालीस": 43, "चवालीस": 44, "पैंतालीस": 45, "छियालीस": 46, "सैंतालीस": 47, "अड़तालीस": 48, "उनचास": 49, "पचास": 50,
                "इक्यावन": 51, "बावन": 52, "तिरेपन": 53, "चौवन": 54, "पचपन": 55, "छप्पन": 56, "सत्तावन": 57, "अट्ठावन": 58, "उनसठ": 59, "साठ": 60,
                "twenty": 20, "twenty one": 21, "twenty two": 22, "twenty three": 23, "twenty four": 24, "twenty five": 25,
                "thirty": 30, "thirty one": 31, "thirty two": 32, "thirty three": 33, "thirty four": 34, "thirty five": 35,
                "forty": 40, "forty five": 45, "fifty": 50, "fifty five": 55,
                "sixty": 60, "sixty five": 65, "seventy": 70, "eighty": 80
            }
            for w, num in word_num_map.items():
                if re.search(r"(?:^|[^\w\u0900-\u097F])" + re.escape(w) + r"(?:[^\w\u0900-\u097F]|$)", u_lower):
                    age_val = num
                    break

        if age_val:
            state.demographics["age"] = age_val

        # 2. Gender extraction (Devanagari + English + Marathi + Hinglish transliterations)
        u_clean_gender = re.sub(r"[।,;:\.\?!()\"'/\-_।॥]", " ", u_lower)
        gender_words_in_utterance = set(u_clean_gender.strip().split())

        male_tokens = [
            "पुरुष", "मेल", "लड़का", "आदमी", "मर्द", "जेंट्स", "जेंटलमैन", "बॉय", "पुरूष", "मुलगा", "पुरुष",
            "male", "man", "men", "boy", "guy", "gents", "gentleman", "purush", "aadmi", "admi", "ladka", "mard", "mr"
        ]
        female_tokens = [
            "महिला", "स्त्री", "फीमेल", "फिमेल", "लड़की", "औरत", "लेडी", "गर्ल", "नारी", "सुश्री", "मुलगी",
            "female", "woman", "women", "lady", "girl", "aurat", "stri", "mahila", "ladki", "nari", "mrs", "ms", "miss"
        ]

        is_male = any(tok in gender_words_in_utterance or tok in u_clean_gender for tok in male_tokens)
        is_female = any(tok in gender_words_in_utterance or tok in u_clean_gender for tok in female_tokens)

        if is_female and not is_male:
            state.demographics["gender"] = "महिला (Female)"
        elif is_male and not is_female:
            state.demographics["gender"] = "पुरुष (Male)"
        elif is_female and is_male:
            state.demographics["gender"] = "महिला (Female)" if any(w in u_clean_gender for w in ["महिला", "female", "फीमेल", "woman", "स्त्री", "lady", "मुलगी"]) else "पुरुष (Male)"

        # 3. Clean Name extraction
        name_already_set = bool(state.demographics.get("name"))
        explicit_name_intro = any(re.search(r"(?:^|[^\w\u0900-\u097F])" + re.escape(w) + r"(?:[^\w\u0900-\u097F]|$)", u_lower) for w in ["मेरा नाम", "माझे नाव", "माझं नाव", "माझ नाव", "my name is", "my name", "naam", "नाम", "नाव", "i am", "i'm", "this is", "name is", "name"])
        is_identity_turn = getattr(state, "current_question_id", "") in ["COM_IDENTITY", "FU_IDENTIFY", "COM_CONSENT"]

        if not name_already_set or explicit_name_intro:
            # First attempt: Direct regex match for explicit name patterns
            # e.g., "मेरा नाम ईश्वरी है।", "माझे नाव ईश्वरी आहे", "mera naam ishwari", "नाम ईश्वरी", "my name is rahul"
            direct_match = re.search(
                r"(?:मेरा\s*नाम|माझे\s*नाव|माझं\s*नाव|माझ\s*नाव|my\s*name\s*is|my\s*name|naam\s*is|mera\s*naam\s*hai|mera\s*naam|naam|नाम|नाव)\s*(?:is|है|आहे|:|का)?\s*([A-Za-z\u0900-\u0963\u0966-\u097F]+(?:\s+[A-Za-z\u0900-\u0963\u0966-\u097F]+)?)\s*(?:है|आहे|हूँ|hoon|hai|ji|जी|$|[।,;\.\?!])",
                utterance,
                re.IGNORECASE
            )
            if direct_match:
                cand = direct_match.group(1).strip()
                cand = re.sub(r"[।,;:\.\?!()\"'/\-_।॥\u0964\u0965]", " ", cand).strip()
                cand_tokens = [w for w in cand.split() if self._is_valid_name_token(w) and w.lower() not in {"जी", "ji", "jee", "श्री", "श्रीमती", "सौ", "कु", "मिस्टर", "mr", "mrs", "miss", "dr", "डॉ"}]
                if cand_tokens:
                    candidate_full = " ".join(cand_tokens[:2])
                    if self._is_valid_patient_name(candidate_full):
                        state.demographics["name"] = candidate_full

            if not state.demographics.get("name") and (explicit_name_intro or getattr(state, "current_question_id", "") in ["COM_IDENTITY", "FU_IDENTIFY"]):
                # Second attempt: Extract candidate only when asking for identity or explicit intro
                name_clean = re.sub(r"[।,;:\.\?!()\"'/\-_।॥\u0964\u0965]", " ", utterance)

                stop_phrases = [
                    "मेरा नाम", "मेरी उम्र", "माझे नाव", "माझं नाव", "माझ नाव", "माझे वय", "नाव", "नाम", "my name is", "my name", "i am", "name is", "name", "i'm", "this is", "naam", "nav",
                    "माय नेम इज़", "माय नेम इज", "माय नेम इस", "माय नेम", "माय एज इज़", "माय एज इज", "माय एज इस", "माय एज", "माय", "आई एम", "आय एम",
                    "years old", "years", "old", "age", "saal", "varsh", "sal", "umra", "umar", "vay", "वय", "ayu",
                    "जी", "ji", "jee", "हाँ", "हां", "haan", "ha", "हो", "होय", "चालेल", "बरं", "बर", "नक्की"
                ]

                for rem in stop_phrases:
                    name_clean = re.sub(r"(?:^|[^\w\u0900-\u0963\u0966-\u097F])" + re.escape(rem) + r"(?:[^\w\u0900-\u0963\u0966-\u097F]|$)", " ", name_clean, flags=re.IGNORECASE)

                candidate_tokens = [
                    w for w in name_clean.strip().split()
                    if self._is_valid_name_token(w) and w.lower() not in {"जी", "ji", "jee", "श्री", "श्रीमती", "सौ", "कु", "मिस्टर", "mr", "mrs", "miss", "dr", "डॉ"}
                ]

                # Only accept if candidate tokens are strictly valid names
                if candidate_tokens and len(candidate_tokens) <= 2:
                    candidate_full = " ".join(candidate_tokens[:2])
                    if self._is_valid_patient_name(candidate_full):
                        state.demographics["name"] = candidate_full

        # 4. Intelligent Indian First-Name Gender Auto-Detection & Auto-Correction
        detected_name = state.demographics.get("name", "").strip()
        if detected_name:
            inferred_gender = self._infer_gender_from_name(detected_name)
            if inferred_gender:
                state.demographics["gender"] = inferred_gender

    def _infer_gender_from_name(self, name: str) -> Optional[str]:
        """
        Intelligently infer and auto-correct patient Gender from Indian First Names
        in Marathi / Hindi / English (e.g., ईश्वरी, Ishwari, Dnyaneshwari, Pooja, Priya, Chetan, Ramesh).
        """
        if not name:
            return None

        clean_name = re.sub(r"[।,;:\.\?!()\"'/\-_।॥\u0964\u0965]", " ", name).strip()
        tokens = clean_name.split()
        if not tokens:
            return None

        first_name = tokens[0].lower().strip()

        # 1. Distinctive Female Names Dictionary (Devanagari + English / Transliteration)
        female_names = {
            # Devanagari Female First Names
            "ईश्वरी", "ज्ञानेश्वरी", "ज्ञानदा", "पूजा", "प्रिया", "अंजली", "स्नेहल", "कविता", "सुनीता",
            "अनिता", "राणी", "नेहा", "दिव्या", "स्वाती", "स्वाति", "आरती", "शीतल", "तन्वी", "प्रणिता",
            "वैष्णवी", "राधा", "साक्षी", "श्रद्धा", "संगीता", "मंजू", "रेखा", "मीना", "सीमा", "आशा",
            "उषा", "लता", "गीता", "दीपा", "रुपाली", "रूपाली", "प्राजक्ता", "सायली", "अश्विनी", "सोनाली",
            "कोमल", "ऋतुजा", "प्रियांका", "प्रियंका", "अमृता", "निशा", "रिंकू", "टीना", "रिया", "सोनम",
            "दीक्षा", "श्रुति", "स्मृती", "स्मृति", "शालिनी", "काजल", "पायल", "भवानी", "लक्ष्मी",
            "सरस्वती", "पार्वती", "दुर्गा", "गायत्री", "तेजस्वी", "अनुराधा", "मंदा", "प्रतिभा", "विजया",
            "शारदा", "सुमन", "पूनम", "सुप्रिया", "मानसी", "कल्याणी", "हर्षा", "हर्षदा", "वैदेही",
            "ऐश्वर्या", "नम्रता", "रुचिका", "मेघा", "शिल्पा", "स्नेहा", "चेतना", "रेश्मा", "शीला",
            "सुशीला", "ममता", "सरिता", "ललिता", "सुजाता", "अनुष्का", "अलका", "कल्पना", "अल्पना",
            "वंदना", "साधना", "भावना", "दीपाली", "जयश्री", "भाग्यश्री", "धनश्री", "राजश्री", "मयुरी",
            "योगिता", "अनिषा", "कृतिका", "सृष्टी", "दृष्टी", "निकिता", "ऋचा", "दृष्टि", "तनुजा",
            "पल्लवी", "गौरी", "तन्मयी", "चिन्मयी", "मृण्मयी", "ईशा", "श्रेया", "ख्याती", "काव्या",
            "लावण्या", "दृश्या", "अवनी", "आरोही", "सिया", "कियारा", "अनन्या", "अदिती", "अदिति",
            "राशी", "दामिनी", "यामिनी", "अपूर्वा", "श्रावणी", "वेदांती", "सानिका", "जान्हवी", "मुग्धा",
            "ऋद्धि", "सिद्धि", "अक्षरा", "अक्षिता", "अंकिता", "अन्विता", "अमिशा", "अपर्णा", "उमा",
            "कमला", "कावेरी", "किरणमयी", "कुमुद", "कुसुम", "चित्रा", "छाया", "जागृती", "ज्योती", "ज्योत्स्ना",
            "तपस्या", "तन्मय", "तृप्ती", "तृषा", "दीक्षिता", "देविका", "नंदिनी", "नयना", "नर्मदा",
            "नीलिमा", "पद्मा", "पद्मिनी", "पारुल", "पुष्पा", "पूर्णिमा", "प्रज्ञा", "प्रभा", "प्राची",
            "प्रेरणा", "बबीता", "बिंदिया", "भारती", "मंगला", "मधु", "मधुरा", "मनीषा", "माला",
            "माधुरी", "मीनल", "मुस्कान", "याचिका", "युक्ता", "रजनी", "रंजना", "रश्मी", "रागिणी",
            "राधिका", "रुक्मिणी", "रूपा", "रेणुका", "रोहिणी", "वसंत", "वसुंधरा", "वाणी", "विद्या",
            "विनीता", "वृषाली", "शकुंतला", "शमी", "शांता", "शिखा", "शोभा", "श्रवंती", "संस्कृती",
            "संध्या", "संपदा", "संयोगिता", "समीक्षा", "सरोज", "सावित्री", "सुवर्णा", "सौम्या", "हर्षिका",
            "हेमा", "हेमलता",

            # English / Roman Transliterations
            "ishwari", "eshwari", "dnyaneshwari", "dnyanada", "pooja", "puja", "priya", "anjali",
            "snehal", "kavita", "sunita", "anita", "rani", "neha", "divya", "swati", "aarti", "arti",
            "shital", "sheetal", "tanvi", "pranita", "vaishnavi", "radha", "sakshi", "shraddha",
            "sangeeta", "sangita", "manju", "rekha", "meena", "mina", "seema", "sima", "asha",
            "usha", "lata", "geeta", "gita", "deepa", "dipa", "rupali", "prajakta", "sayali",
            "ashwini", "sonali", "komal", "rutuja", "priyanka", "amrita", "nisha", "rinku", "tina",
            "riya", "sonam", "deeksha", "diksha", "shruti", "smriti", "shalini", "kajal", "payal",
            "bhawani", "laxmi", "lakshmi", "saraswati", "parvati", "durga", "gayatri", "tejaswi",
            "anuradha", "manda", "pratibha", "vijaya", "sharda", "suman", "poonam", "supriya",
            "manasi", "mansi", "kalyani", "harsha", "harshada", "vaidehi", "aishwarya", "namrata",
            "ruchika", "megha", "shilpa", "sneha", "chetna", "reshma", "sheela", "shila", "sushila",
            "mamta", "sarita", "lalita", "sujata", "anushka", "alka", "kalpana", "alpana", "vandana",
            "sadhana", "bhavana", "bhavna", "deepali", "dipali", "jayashree", "jayshree", "bhagyashree",
            "dhanashree", "rajashree", "mayuri", "yogita", "anisha", "kritika", "krutika", "srushti",
            "drishti", "nikita", "richa", "tanuja", "pallavi", "gauri", "gowri", "tanmayi", "chinmayi",
            "mrunmayi", "isha", "shreya", "khyati", "kavya", "lavanya", "drishya", "avani", "aarohi",
            "siya", "kiara", "ananya", "aditi", "rashi", "damini", "yamini", "apoorva", "apurva",
            "shravani", "vedanti", "sanika", "janhvi", "janhavi", "mugdha", "riddhi", "siddhi",
            "akshara", "akshita", "ankita", "anvita", "aparna", "uma", "kumud", "kusum", "chhaya",
            "jyoti", "trupti", "devika", "nandini", "nayana", "nilima", "padma", "parul", "pushpa",
            "pragya", "prachi", "prerna", "babita", "bharti", "mangala", "madhu", "madhuri", "manisha",
            "minal", "muskan", "rajni", "ranjana", "rashmi", "radhika", "rukmini", "rupa", "renuka",
            "rohini", "vani", "vidya", "vinita", "vrushali", "shikha", "shobha", "sandhya", "sampada",
            "samiksha", "saroj", "savitri", "suvarna", "saumya", "hema", "hemlata"
        }

        # 2. Distinctive Male Names Dictionary (Devanagari + English / Transliteration)
        male_names = {
            # Devanagari Male First Names
            "गोविंद", "रमेश", "सुरेश", "महेश", "गणेश", "चेतन", "राहुल", "अमित", "सचिन", "रोहित",
            "विराट", "अजय", "विजय", "संजय", "विकास", "प्रकाश", "प्रदीप", "संदीप", "राजेश", "दिनेश",
            "मुकेश", "राकेश", "अनिल", "सुनील", "मनोज", "विनोद", "अशोक", "किशोर", "नितीन", "प्रमोद",
            "प्रशांत", "अमोल", "अतुल", "समीर", "विशाल", "स्वप्निल", "तुषार", "ओंकार", "अनिकेत",
            "अभिषेक", "गौरव", "ऋषिकेश", "रोहन", "अक्षय", "आदित्य", "हर्षल", "हर्ष", "निखिल", "मयूर",
            "वैभव", "शुभम", "सूरज", "दीपक", "पवन", "सागर", "आनंद", "प्रवीण", "योगेश", "ज्ञानेश्वर",
            "ज्ञानेश", "ईश्वर", "भरत", "लक्ष्मण", "शत्रुघ्न", "अर्जुन", "भीम", "नकुल", "सहदेव",
            "कर्ण", "युधिष्ठिर", "शंकर", "विष्णु", "ब्रह्मा", "इंद्र", "वरुण", "अग्नि", "सूर्य",
            "चंद्र", "कार्तिक", "राघव", "माधव", "केशव", "गोपाल", "वासुदेव", "दामोदर", "श्रीधर",
            "जनार्दन", "मुरली", "बलराम", "गिरिधर", "विश्वनाथ", "कैलाश", "चंद्रकांत", "सूर्यकांत",
            "शशिकांत", "लक्ष्मीकांत", "रमाकांत", "उमाकांत", "दीनानाथ", "बद्रीनाथ", "सोमनाथ", "अमरनाथ",
            "केदारनाथ", "जगन्नाथ", "रंगनाथ", "विश्वंभर", "दत्तात्रेय", "दत्त", "गुरुदत्त", "रामदास",
            "हरिदास", "कालिदास", "तुलसीदास", "सूरदास", "कबीर", "तुकाराम", "नामदेव", "एकनाथ",
            "रामेश्वर", "सोमेश्वर", "महादेव", "सदाशिव", "त्र्यंबक", "मल्लिकार्जुन", "भीमाशंकर",
            "नागेश", "सिद्धेश", "योगेंद्र", "नरेंद्र", "देवेंद्र", "जितेंद्र", "धर्मेंद्र", "सुरेंद्र",
            "वीरेंद्र", "सत्येंद्र", "गजेंद्र", "भूपेंद्र", "राजेंद्र", "महेंद्र", "उपेंद्र", "दिगंबर",
            "पीतांबर", "श्रीकांत", "रविकांत", "सुशांत", "निशिकांत", "जयंत", "हेमंत", "अनंत",
            "वेदांत", "सिद्धांत", "दीक्षांत", "निशांत", "प्रशांत", "दुष्यंत", "यशवंत", "बलवंत",
            "कुलवंत", "भगवंत", "जयवंत", "गुणवंत", "हनुमंत",

            # English / Roman Transliterations
            "govind", "ramesh", "suresh", "mahesh", "ganesh", "chetan", "rahul", "amit", "sachin",
            "rohit", "virat", "ajay", "vijay", "sanjay", "vikas", "prakash", "pradeep", "sandeep",
            "rajesh", "dinesh", "mukesh", "rakesh", "anil", "sunil", "manoj", "vinod", "ashok",
            "kishore", "nitin", "pramod", "prashant", "amol", "atul", "sameer", "samir", "vishal",
            "swapnil", "tushar", "omkar", "aniket", "abhishek", "gaurav", "rushikesh", "hrishikesh",
            "rohan", "akshay", "aditya", "harshal", "harsh", "nikhil", "mayur", "vaibhav", "shubham",
            "suraj", "deepak", "dipak", "pawan", "sagar", "anand", "praveen", "pravin", "yogesh",
            "dnyaneshwar", "dnyanesh", "ishwar", "eshwar", "bharat", "laxman", "lakshman", "arjun",
            "shankar", "vishnu", "raghav", "madhav", "keshav", "gopal", "kailash", "chandrakant",
            "shashikant", "laxmikant", "somnath", "jagannath", "tukaram", "namdev", "eknath",
            "rameshwar", "mahadev", "narendra", "devendra", "jitendra", "dharmendra", "surendra",
            "rajendra", "mahendra", "shrikant", "hemant", "vedant", "siddhant", "nishant", "yashwant"
        }

        if first_name in female_names:
            return "महिला (Female)"
        if first_name in male_names:
            return "पुरुष (Male)"

        # 3. Morphological & Suffix Heuristics for Indian Names
        female_suffixes = (
            "ी", "ई", "श्री", "वती", "मती", "िका", "ता", "दा", "जा", "ना", "या", "ला",
            "shree", "shri", "wati", "mati", "ika", "ita", "lata", "priya", "kavita", "mala"
        )
        male_suffixes = (
            "ेश्वर", "ेश", "ेंद्र", "कांत", "राज", "कुमार", "राव", "नाथ", "प्रसाद", "लाल", "दास", "देव",
            "eshwar", "esh", "endra", "raj", "kumar", "nath", "prasad", "lal", "das", "dev", "want", "vant"
        )

        male_exceptions = {"राम", "कृष्ण", "गोविंद", "गणपति", "मारुति", "रवि", "हरि", "ऋषि", "ऋत्विज", "shiva", "rama", "krishna", "ganpati", "maruti", "ravi", "hari", "rishi"}

        for sfx in female_suffixes:
            if first_name.endswith(sfx) and len(first_name) > len(sfx) + 1:
                if first_name not in male_exceptions:
                    return "महिला (Female)"

        for sfx in male_suffixes:
            if first_name.endswith(sfx) and len(first_name) > len(sfx) + 1:
                return "पुरुष (Male)"

        return None

    def _extract_clinical_slots(self, state: SehatSessionState, utterance: str):
        u_lower = utterance.lower()
        
        # Symptoms (Hindi + English + Transliterated keywords)
        symptom_map = {
            "polydipsia_excessive_thirst": [
                "प्यास", "thirst", "thirsty", "pyas", "gala sukh", "सूख", "water", "पानी", "excessive thirst", "बहुत प्यास",
                "drinking a lot of water", "dry mouth", "extreme thirst"
            ],
            "polyuria_frequent_urination": [
                "पेशाब", "urine", "peshab", "toilet", "mutra", "टॉयलेट", "peeing", "frequent urine", "washroom", "बार-बार पेशाब",
                "frequent urination", "peeing a lot", "wake up to pee", "night urination"
            ],
            "fatigue_weakness": [
                "थकान", "कमजोरी", "fatigue", "tired", "tiredness", "kamjori", "weakness", "सुस्ती", "lethargy", "weak", "कमज़ोरी",
                "exhausted", "low energy", "feeling tired"
            ],
            "blurred_vision": [
                "धुंधला", "धुंधलापन", "blur", "blurred", "blurry", "vision", "nazar", "aankh", "आँख", "eye", "eyes", "नजर", "नज़र",
                "cannot see clearly", "vision problem", "blurred vision"
            ],
            "weight_loss_gain": [
                "वजन", "वेट", "weight", "wajan", "patla", "mota", "weight loss", "weight gain", "loss", "vajan",
                "losing weight", "gaining weight"
            ],
            "delayed_wound_healing": [
                "घाव", "चोट", "wound", "healing", "ulcer", "chot", "ghav", "theek nahi", "नासूर", "injury", "infection", "cuts",
                "slow healing", "delayed healing", "wound not healing", "ulcers"
            ],
            "numbness_tingling": [
                "सुन्न", "झनझनाहट", "numbness", "tingling", "sunn", "jhanjhanahat", "पैरों में जलन", "burning", "pins and needles", "numb", "सुन्नपन",
                "numb feet", "tingling sensation", "burning feet"
            ],
            "hypoglycemia_episodes": [
                "पसीना", "कांप", "घबराहट", "चक्कर", "low sugar", "hypo", "शुगर कम", "sweating", "shaking", "trembling", "dizziness", "giddiness",
                "shivering", "fainting feeling", "shaky"
            ]
        }

        # Check for explicit symptom denials (No Symptoms reported)
        symptom_denial_keywords = [
            "कोई लक्षण नहीं", "लक्षण नहीं है", "कोई समस्या नहीं", "कोई प्रॉब्लम नहीं", "no symptoms",
            "i have no symptoms", "no issue", "no problem", "kuch nahi hai", "bilkul theek",
            "कोई तकलीफ नहीं", "सब ठीक है", "काही त्रास नाही", "लक्षणे नाहीत"
        ]
        if any(k in u_lower for k in symptom_denial_keywords):
            if "all_symptoms" not in state.symptoms_denied:
                state.symptoms_denied.append("all_symptoms")
            state.context_memory["no_symptoms"] = True

        for sym, keywords in symptom_map.items():
            if any(k in u_lower for k in keywords):
                if sym not in state.symptoms_reported:
                    state.symptoms_reported.append(sym)
                    if sym in ["polydipsia_excessive_thirst", "polyuria_frequent_urination", "delayed_wound_healing", "hypoglycemia_episodes"]:
                        if sym not in state.risk_signals:
                            state.risk_signals.append(f"Risk: {sym}")

        if "numbness_tingling" in state.symptoms_reported or "delayed_wound_healing" in state.symptoms_reported:
            state.context_memory["foot_issues"] = True

        # Mark symptom-related topics complete if matched
        if any(k in u_lower for k in ["प्यास", "पेशाब", "thirst", "urine", "water", "peeing"]):
            if "thirst_and_urination" not in state.completed_topics:
                state.completed_topics.append("thirst_and_urination")
            if "classic_symptoms" not in state.completed_topics:
                state.completed_topics.append("classic_symptoms")

        if any(k in u_lower for k in ["थकान", "धुंधला", "कमजोरी", "fatigue", "vision", "tired", "blur", "नजर", "eyes", "eye"]):
            if "vision_and_fatigue" not in state.completed_topics:
                state.completed_topics.append("vision_and_fatigue")
            if "energy_and_vision" not in state.completed_topics:
                state.completed_topics.append("energy_and_vision")

        if any(k in u_lower for k in ["घाव", "सुन्न", "झनझनाहट", "wound", "numb", "tingling", "healing", "जलन"]):
            if "neuropathy_and_wounds" not in state.completed_topics:
                state.completed_topics.append("neuropathy_and_wounds")
            if "healing_and_numbness" not in state.completed_topics:
                state.completed_topics.append("healing_and_numbness")

        # Blood Sugar Readings
        sugar_match = re.search(r"\b(sugar|शुगर|fasting|pp|sugar\s*level|glucose|blood\s*sugar|hba1c)?\s*([6-9]\d|[1-5]\d{2})\b", u_lower)
        if sugar_match:
            val_str = sugar_match.group(2)
            try:
                val = int(val_str)
                state.blood_sugar_readings.append({"value": val, "raw": sugar_match.group(0)})
                state.context_memory["recent_sugar"] = val
                if val >= 250:
                    state.sugar_category = "severe_hyperglycemia"
                    state.context_memory["has_high_sugar"] = True
                    state.risk_signals.append(f"Severely Elevated Blood Sugar: {val} mg/dL")
                elif val >= 180:
                    state.sugar_category = "hyperglycemia"
                    state.context_memory["has_high_sugar"] = True
                    state.risk_signals.append(f"Elevated Blood Sugar: {val} mg/dL")
                elif val < 70:
                    state.sugar_category = "hypoglycemia"
                    state.context_memory["has_low_sugar"] = True
                    state.risk_signals.append(f"Hypoglycemia (Low Sugar): {val} mg/dL")
                else:
                    state.sugar_category = "normal_or_controlled"

                if "blood_sugar_readings" not in state.completed_topics:
                    state.completed_topics.append("blood_sugar_readings")
                if "previous_testing" not in state.completed_topics:
                    state.completed_topics.append("previous_testing")
            except ValueError:
                pass

        # Type 1 / Type 2 Diabetes Classification
        if state.current_question_id == "KD_DIABETES_TYPE" or any(w in u_lower for w in ["टाइप 1", "type 1", "type1", "type one", "टाइप 2", "type 2", "type2", "type two"]):
            if any(w in u_lower for w in ["टाइप 1", "type 1", "type1", "टाइप1", "type one"]) or (state.current_question_id == "KD_DIABETES_TYPE" and "1" in u_lower and "2" not in u_lower):
                state.diabetes_type = "टाइप 1 (Type 1)"
                if "diabetes_type" not in state.completed_topics:
                    state.completed_topics.append("diabetes_type")
            elif any(w in u_lower for w in ["टाइप 2", "type 2", "type2", "टाइप2", "type two"]) or (state.current_question_id == "KD_DIABETES_TYPE" and "2" in u_lower and "1" not in u_lower):
                state.diabetes_type = "टाइप 2 (Type 2)"
                if "diabetes_type" not in state.completed_topics:
                    state.completed_topics.append("diabetes_type")
            elif any(w in u_lower for w in ["पता नहीं", "मालूम नहीं", "not sure", "unsure", "याद नहीं", "don't know", "dont know"]):
                state.diabetes_type = "अनिर्धारित (Unspecified)"
                if "diabetes_type" not in state.completed_topics:
                    state.completed_topics.append("diabetes_type")

        # Duration Extraction (Strictly only for known diabetics, never for demographics or non-diabetics)
        if state.branch == "known_diabetic" or state.current_question_id in ["KD_DURATION", "A_DURATION"]:
            is_age_context = bool(re.search(r"\b(उम्र|आयु|age|aged|old|साल\s*का|साल\s*की|साल\s*के|years\s*old)\b", u_lower))
            if state.current_question_id not in ["COM_DEMOGRAPHICS", "Q2_IDENTITY", "COM_CONSENT"] and not is_age_context:
                dur_match = re.search(r"(\d{1,2})\s*(साल|वर्ष|महीने|months?|years?|saal|varsh|mahine|yrs?|yr)", u_lower)
                if dur_match:
                    state.diabetes_history = dur_match.group(0)
                    if "diabetes_duration" not in state.completed_topics:
                        state.completed_topics.append("diabetes_duration")
        else:
            # For non-diabetic or unsure branch, diabetes duration must not be populated
            state.diabetes_history = None

        # Medications (English + Hindi + Brand names)
        if any(w in u_lower for w in ["दवा", "tablet", "tablets", "medicine", "medicines", "metformin", "gliclazide", "glimepiride", "गोली", "meds", "pills", "पिल्स", "टैबलेट", "dawa", "dawai", "oral meds"]):
            if "Oral Anti-Diabetic Medication" not in state.medications:
                state.medications.append("Oral Anti-Diabetic Medication")
            state.medication_category = "oral_hypoglycemic"
            state.context_memory["has_oral_meds"] = True
            if "medications" not in state.completed_topics:
                state.completed_topics.append("medications")
        if any(w in u_lower for w in ["इंसुलिन", "insulin", "injection", "सुई", "insulin pen"]):
            if "Insulin Therapy" not in state.medications:
                state.medications.append("Insulin Therapy")
            state.medication_category = "insulin"
            state.context_memory["has_insulin"] = True
            if "medications" not in state.completed_topics:
                state.completed_topics.append("medications")

        # Family History
        is_family_q = (
            state.current_question_id in ["UN_FAMILY_HISTORY", "ND_FAMILY_HISTORY", "KD_FAMILY_HISTORY"]
            or "family" in (state.current_question_id or "").lower()
        )
        has_family_words = any(w in u_lower for w in [
            "माता", "पिता", "family", "father", "mother", "brother", "sister", "parents", "खानदान", "परिवार",
            "पापा", "मम्मी", "भाई", "बहन", "दादी", "दादा", "नानी", "नाना", "genetics", "hereditary",
            "khandan", "parivar", "family history", "मदर", "फादर", "डैडी"
        ])

        if is_family_q or has_family_words:
            is_neg = any(re.search(pat, u_lower) for pat in [
                r"\b(no|nahi|nahin|na|never|none|nobody|negative|not)\b",
                r"(नहीं|नही|नो|ना|कभी\s*नहीं|किसी\s*को\s*नहीं|किसी\s*को\s*भी\s*नहीं|कोई\s*नहीं|नहीं\s*है|नहीं\s*थी|नहीं\s*रही|समस्या\s*नहीं)"
            ])
            is_pos = any(re.search(pat, u_lower) for pat in [
                r"\b(yes|yeah|yup|haan|ha|hai|positive)\b",
                r"(हाँ|हां|है|थी|था|बिल्कुल|माता\s*को|पिता\s*को|मम्मी\s*को|पापा\s*को|भाई\s*को|बहन\s*को|परिवार\s*में\s*है|फैमिली\s*में\s*है)"
            ])

            if is_neg and not is_pos:
                state.family_history = False
                if "family_history" not in state.completed_topics:
                    state.completed_topics.append("family_history")
            elif is_pos and not is_neg:
                state.family_history = True
                if "family_history" not in state.completed_topics:
                    state.completed_topics.append("family_history")
            elif is_neg and is_pos:
                if any(w in u_lower for w in ["पापा को है", "मम्मी को है", "पिता को", "माता को", "भाई को", "बहन को", "फादर को", "मदर को", "family me hai", "father has", "mother has", "yes"]):
                    state.family_history = True
                else:
                    state.family_history = False
                if "family_history" not in state.completed_topics:
                    state.completed_topics.append("family_history")
            elif is_family_q:
                if any(w in u_lower for w in ["हाँ", "हां", "yes", "ha", "haan", "था", "थी", "है"]):
                    state.family_history = True
                else:
                    state.family_history = False
                if "family_history" not in state.completed_topics:
                    state.completed_topics.append("family_history")
            state.context_memory["family_history"] = state.family_history

        # Pregnancy History (Step 1: check if ever pregnant)
        is_preg_q = (
            state.current_question_id in ["UN_PREGNANCY_HISTORY", "ND_PREGNANCY_HISTORY", "KD_PREGNANCY_HISTORY"]
            or "pregnancy" in (state.current_question_id or "").lower()
        )
        has_preg_words = any(w in u_lower for w in [
            "माँ बनने", "गर्भावस्था", "प्रेगनेंसी", "pregnancy", "डिलीवरी", "pregnant", "प्रेग्नेंट",
            "बच्चा", "बच्चे", "डिलीवर", "डिलिवरी", "माँ हूँ", "मां हूं", "mother of"
        ])

        if is_preg_q or has_preg_words:
            is_preg_neg = any(re.search(pat, u_lower) for pat in [
                r"\b(no|nahi|nahin|na|never|not|none|unmarried|single)\b",
                r"(नहीं|नही|नो|ना|कभी\s*नहीं|नहीं\s*रही|नहीं\s*हुई|शादी\s*नहीं|अविवाहित|कुंवारी|बच्चा\s*नहीं|कोई\s*नहीं|प्रेग्नेंट\s*नहीं|प्रेगनेंसी\s*नहीं|ऐसी\s*कोई\s*बात\s*नहीं|कुछ\s*नहीं)"
            ])
            is_preg_pos = any(re.search(pat, u_lower) for pat in [
                r"\b(yes|yeah|yup|haan|ha|delivery|pregnant|baby|child|children)\b",
                r"(हाँ|हां|थी|था|है|हुई\s*थी|हुई\s*है|बच्चा|बच्चे|बेटी|बेटा|डिलीवरी|प्रेग्नेंट\s*थी|प्रेगनेंसी\s*रही|माँ\s*हूँ|मां\s*हूं|दो\s*बच्चे|एक\s*बच्चा)"
            ])

            if is_preg_neg and not is_preg_pos:
                state.pregnancy_history = False
                state.gestational_history = False
                if "pregnancy_history" not in state.completed_topics:
                    state.completed_topics.append("pregnancy_history")
                if "gestational_diabetes" not in state.completed_topics:
                    state.completed_topics.append("gestational_diabetes")
            elif is_preg_pos and not is_preg_neg:
                state.pregnancy_history = True
                if "pregnancy_history" not in state.completed_topics:
                    state.completed_topics.append("pregnancy_history")
            elif is_preg_neg and is_preg_pos:
                if any(w in u_lower for w in ["नहीं रही", "नहीं हुई", "शादी नहीं हुई", "बच्चा नहीं", "प्रेग्नेंट नहीं", "never pregnant", "not pregnant", "कभी नहीं रही"]):
                    state.pregnancy_history = False
                    state.gestational_history = False
                    if "pregnancy_history" not in state.completed_topics:
                        state.completed_topics.append("pregnancy_history")
                    if "gestational_diabetes" not in state.completed_topics:
                        state.completed_topics.append("gestational_diabetes")
                elif any(w in u_lower for w in ["हाँ", "हां", "yes", "2 साल पहले", "बच्चा है", "डिलीवरी हुई थी", "दो बच्चे"]):
                    state.pregnancy_history = True
                    if "pregnancy_history" not in state.completed_topics:
                        state.completed_topics.append("pregnancy_history")
                else:
                    state.pregnancy_history = False
                    state.gestational_history = False
                    if "pregnancy_history" not in state.completed_topics:
                        state.completed_topics.append("pregnancy_history")
                    if "gestational_diabetes" not in state.completed_topics:
                        state.completed_topics.append("gestational_diabetes")
            elif is_preg_q:
                if any(w in u_lower for w in ["हाँ", "हां", "yes", "ha", "haan", "था", "थी", "है"]):
                    state.pregnancy_history = True
                    if "pregnancy_history" not in state.completed_topics:
                        state.completed_topics.append("pregnancy_history")
                else:
                    state.pregnancy_history = False
                    state.gestational_history = False
                    if "pregnancy_history" not in state.completed_topics:
                        state.completed_topics.append("pregnancy_history")
                    if "gestational_diabetes" not in state.completed_topics:
                        state.completed_topics.append("gestational_diabetes")
            state.context_memory["has_pregnancy"] = state.pregnancy_history

        # Gestational Diabetes Follow-up (Step 2: check if blood sugar elevated during pregnancy)
        is_gest_q = (
            state.current_question_id in ["UN_GESTATIONAL", "ND_GESTATIONAL", "KD_GESTATIONAL"]
            or "gestational" in (state.current_question_id or "").lower()
        )
        has_gest_words = any(w in u_lower for w in [
            "गेस्टेशनल", "gestational", "गर्भावस्था के दौरान शुगर", "गर्भावस्था में शुगर",
            "प्रेगनेंसी में शुगर", "प्रेगनेंसी के दौरान शुगर", "pregnancy diabetes", "gdm"
        ])

        if is_gest_q or has_gest_words:
            is_gest_neg = any(re.search(pat, u_lower) for pat in [
                r"\b(no|nahi|nahin|na|never|normal|not|none)\b",
                r"(नहीं|नही|नो|ना|नॉर्मल|कभी\s*नहीं|सामान्य|ठीक\s*था|नहीं\s*थी|नहीं\s*बढ़ी|नहीं\s*बढ़ा|कोई\s*समस्या\s*नहीं)"
            ])
            is_gest_pos = any(re.search(pat, u_lower) for pat in [
                r"\b(yes|yeah|yup|haan|ha|high|elevated|gdm)\b",
                r"(हाँ|हां|थी|था|है|बढ़ी\s*थी|बढ़ी\s*थी|बढ़\s*गई\s*थी|हाई\s*थी|शुगर\s*हुई\s*थी|गेस्टेशनल|डायबिटीज\s*थी)"
            ])

            if is_gest_neg and not is_gest_pos:
                state.gestational_history = False
            elif is_gest_pos and not is_gest_neg:
                state.gestational_history = True
                if "Risk: Gestational Diabetes History" not in state.risk_signals:
                    state.risk_signals.append("Risk: Gestational Diabetes History")
            elif is_gest_neg and is_gest_pos:
                if any(w in u_lower for w in ["नहीं", "नॉर्मल", "normal", "सामान्य"]):
                    state.gestational_history = False
                else:
                    state.gestational_history = True
                    if "Risk: Gestational Diabetes History" not in state.risk_signals:
                        state.risk_signals.append("Risk: Gestational Diabetes History")
            elif is_gest_q:
                if any(w in u_lower for w in ["हाँ", "हां", "yes", "ha", "haan", "था", "थी", "बढ़ी"]):
                    state.gestational_history = True
                    if "Risk: Gestational Diabetes History" not in state.risk_signals:
                        state.risk_signals.append("Risk: Gestational Diabetes History")
                else:
                    state.gestational_history = False

            if "gestational_diabetes" not in state.completed_topics:
                state.completed_topics.append("gestational_diabetes")

    def _finalize_urgency(self, state: SehatSessionState):
        urg_res = self.urgency_engine.evaluate(
            emergency_escalation=state.emergency_escalation,
            risk_signals=state.risk_signals,
            symptoms_reported=state.symptoms_reported,
            blood_sugar_readings=state.blood_sugar_readings,
            family_history=state.family_history,
            gestational_history=state.gestational_history
        )
        state.recommended_urgency = urg_res.get("recommended_urgency", "routine")
        state.urgency_reasons = urg_res.get("urgency_reasons", [])

    def _lookup_question_text(self, qid: str) -> str:
        for branch_list in self.selector.bank.values():
            if isinstance(branch_list, list):
                for q in branch_list:
                    if isinstance(q, dict) and q.get("question_id") == qid:
                        return q.get("question_hi", "")
        if qid == "COM_CONSENT":
            return "नमस्ते, मेरा नाम Diabetes Dost है। मैं Doctor से मिलने से पहले आपकी Diabetes से जुड़ी कुछ Health जानकारी समझने में help करूंगा। क्या आप बातचीत और Audio Recording के लिए सहमत हैं?"
        elif qid == "COM_DEMOGRAPHICS":
            return "धन्यवाद। आपकी सही पहचान और रिकॉर्ड के लिए, कृपया अपना पूरा नाम, उम्र और लिंग बताइए।"
        elif qid == "COM_STATUS":
            return "क्या आपको पहले से डायबिटीज (शुगर की बीमारी) है, या आपको इसके कोई लक्षण महसूस हो रहे हैं, या आपको डायबिटीज नहीं है?"
        return qid


# Global instance
GLOBAL_DIALOGUE_MANAGER = DialogueManager()

