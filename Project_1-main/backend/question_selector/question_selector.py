import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("sehat_question_selector")

class QuestionSelector:
    """
    Context-Aware Dynamic Question Selector for Sehat AI.
    Selects next questions dynamically based on clinical priority, patient branch,
    symptom signals, missing information, and question budget (6-12).
    """
    def __init__(self, question_bank_file: Optional[str] = None):
        self.question_bank_file = question_bank_file or self._find_question_bank()
        self.bank = self._load_bank()

    def _find_question_bank(self) -> str:
        candidates = [
            "data/question_bank.json",
            "../data/question_bank.json",
            "e:/Diabetes/data/question_bank.json",
            "backend/data/question_bank.json"
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return "data/question_bank.json"

    def _load_bank(self) -> Dict[str, Any]:
        if os.path.exists(self.question_bank_file):
            try:
                with open(self.question_bank_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded question bank version {data.get('version', 'unknown')} from {self.question_bank_file}")
                    return data
            except Exception as e:
                logger.error(f"Error loading question bank from {self.question_bank_file}: {e}")
        return {}

    def select_next_question(
        self,
        current_branch: str,
        asked_question_ids: List[str],
        completed_topics: List[str],
        questions_asked_count: int,
        demographics: Dict[str, Any],
        symptoms_reported: List[str],
        risk_signals: List[str],
        max_budget: int = 12,
        context_memory: Optional[Dict[str, Any]] = None,
        sugar_readings: Optional[List[Dict[str, Any]]] = None,
        medications: Optional[List[str]] = None,
        symptoms_denied: Optional[List[str]] = None,
        volunteered_slots: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Dynamically determine the best next question using Context Memory & Clinical Prioritization.
        Enforces:
        1. Mandatory Common Questions (Consent -> Demographics -> Diabetic Status)
        2. Dynamic Context-Driven Scoring & Question Rerouting based on previous answers:
           - Severe Hyperglycemia (>=250 mg/dL) -> Boosts medication adherence, thirst/urination, vision/fatigue
           - Neuropathy Symptoms (Numbness/Tingling/Wounds) -> Boosts neuropathy & wound assessment
           - Hypoglycemia Signals (Shaking/Sweating/<70 mg/dL) -> Boosts hypoglycemia management
           - Insulin Usage -> Boosts medication/hypoglycemia follow-up
           - Positive Family History -> Boosts lifestyle & preventive screening
           - Explicitly Denied Symptoms -> Prunes redundant symptom queries
           - Volunteered / Pre-answered Slots -> Automatically bypassed
        3. Female-only restriction on gestational diabetes & Age safety checks (<18)
        4. Budget limits (Min 6, Target 6-10, Max 12)
        5. Closing Question before normal termination
        """
        context_memory = context_memory or {}
        sugar_readings = sugar_readings or []
        medications = medications or []
        symptoms_denied = symptoms_denied or []
        volunteered_slots = volunteered_slots or []

        # 1. Check Mandatory Common Flow (Only for new patients / initial screening branches)
        if current_branch != "follow_up":
            common_questions = self.bank.get("common", [])
            for q in common_questions:
                qid = q.get("question_id")
                if qid not in asked_question_ids:
                    return q

        # 2. If budget reached (or sufficient info collected after >= 6 turns and closing needed)
        is_closing_asked = any(q.startswith("CLS_") for q in asked_question_ids)
        if questions_asked_count >= (max_budget - 1) and not is_closing_asked:
            return self._get_closing_question(asked_question_ids)

        # 3. Dynamic Context-Aware Candidate Evaluation
        branch_key = current_branch if current_branch in ["known_diabetic", "unsure", "not_diabetic", "follow_up"] else "unsure"
        available_branch_questions = self.bank.get(branch_key, [])

        patient_gender = str(demographics.get("gender", "")).lower()
        is_female = any(w in patient_gender for w in ["महिला", "स्त्री", "female", "woman", "f", "girl", "lady", "फीमेल"])
        patient_age = demographics.get("age")

        # Context Memory Flags
        has_high_sugar = False
        has_low_sugar = False
        recent_sugar_val = None
        if sugar_readings:
            recent_sugar_val = sugar_readings[-1].get("value")
            if isinstance(recent_sugar_val, (int, float)):
                if recent_sugar_val >= 250:
                    has_high_sugar = True
                elif recent_sugar_val < 70:
                    has_low_sugar = True

        has_insulin = any("insulin" in str(m).lower() or "इंसुलिन" in str(m) for m in medications) or bool(context_memory.get("has_insulin"))
        has_neuro_symptoms = any(s in ["numbness_tingling", "delayed_wound_healing", "burning_feet"] for s in symptoms_reported) or bool(context_memory.get("foot_issues"))
        no_symptoms_flag = "all_symptoms" in symptoms_denied or bool(context_memory.get("no_symptoms"))

        # Base Priority Mapping
        priority_map = {"mandatory": 100, "high": 75, "medium": 50, "low": 25}

        scored_candidates = []

        for q in available_branch_questions:
            qid = q.get("question_id")
            topic = q.get("topic")

            # 1. Prevent duplicate questions or already completed/volunteered topics
            if qid in asked_question_ids or topic in completed_topics or topic in volunteered_slots:
                continue

            # 2. Gender and Age Restrictions (Pregnancy & Gestational only for adult females)
            if q.get("gender_restriction") == "female":
                if not is_female:
                    continue
                if patient_age is not None and isinstance(patient_age, (int, float)) and patient_age < 18:
                    continue

            # 3. Prerequisite topic check
            prereq = q.get("prerequisite_topic")
            if prereq and prereq not in completed_topics:
                continue

            # 4. Prune symptom questions if patient explicitly reported no symptoms
            if no_symptoms_flag:
                if topic in ["classic_symptoms", "energy_and_vision", "healing_and_numbness", "thirst_and_urination", "vision_and_fatigue", "neuropathy_and_wounds"]:
                    continue

            # Calculate Dynamic Context Score
            base_score = priority_map.get(q.get("priority", "medium"), 50)
            bonus_score = 0

            # Dynamic Context Rules:
            # Rule A: High Blood Sugar Boost
            if has_high_sugar:
                if topic in ["medications", "blood_sugar_readings", "thirst_and_urination", "vision_and_fatigue"]:
                    bonus_score += 60

            # Rule B: Low Blood Sugar / Hypoglycemia Boost
            if has_low_sugar or "shivering_sweating" in symptoms_reported:
                if topic in ["hypoglycemia_symptoms", "medications", "blood_sugar_readings"]:
                    bonus_score += 70

            # Rule C: Neuropathy / Tingling / Wound Healing Boost
            if has_neuro_symptoms:
                if topic in ["neuropathy_and_wounds", "healing_and_numbness"]:
                    bonus_score += 80

            # Rule D: Insulin User Boost
            if has_insulin:
                if topic in ["medications", "hypoglycemia_symptoms"]:
                    bonus_score += 55

            # Rule E: Positive Family History Boost in Non-Diabetic / Unsure
            if context_memory.get("family_history") is True:
                if topic in ["lifestyle_factors", "physical_activity", "weight_and_lifestyle", "recent_screening", "previous_testing"]:
                    bonus_score += 45

            # Rule F: Female Pregnancy Follow-up Boost
            if is_female and context_memory.get("has_pregnancy") is True and topic == "gestational_diabetes":
                bonus_score += 65

            total_score = base_score + bonus_score
            scored_candidates.append((total_score, q))

        # Sort candidates by total dynamic score descending
        if scored_candidates:
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            chosen_q = scored_candidates[0][1]
            return chosen_q

        # 4. If all branch questions exhausted or sufficient info collected (>= 6 questions asked)
        if not is_closing_asked:
            return self._get_closing_question(asked_question_ids)

        return None

    def _get_closing_question(self, asked_question_ids: List[str]) -> Optional[Dict[str, Any]]:
        closing_list = self.bank.get("closing", [])
        for q in closing_list:
            if q.get("question_id") not in asked_question_ids:
                return q
        return {
            "question_id": "CLS_FINAL_FEEDBACK",
            "topic": "closing_remarks",
            "branch": "closing",
            "question_hi": "क्या आप Doctor को अपनी Health से जुड़ी कोई और Important बात बताना चाहते हैं?",
            "priority": "mandatory",
            "required": True
        }


# Global instance
GLOBAL_QUESTION_SELECTOR = QuestionSelector()

