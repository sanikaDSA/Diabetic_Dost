import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from session_store.patient_registry import GLOBAL_PATIENT_REGISTRY
from dialogue.dialogue_manager import GLOBAL_DIALOGUE_MANAGER
from session_store.session_store import GLOBAL_SESSION_STORE
from question_selector.question_selector import GLOBAL_QUESTION_SELECTOR

print("1. Testing patient save and lookup...")
sid = "test_fu_direct_01"
GLOBAL_DIALOGUE_MANAGER.start_session(sid)
state = GLOBAL_SESSION_STORE.get(sid)
state.demographics = {"name": "प्रकाश देशमुख", "age": 54, "gender": "पुरुष (Male)"}
state.branch = "known_diabetic"
state.diabetes_type = "टाइप 2 (Type 2)"
state.medications = ["Metformin 500mg"]
state.blood_sugar_readings = [{"value": 240, "raw": "240"}]
state.is_completed = True

rec = GLOBAL_PATIENT_REGISTRY.save_patient_visit(state)
print("Saved record:", rec["name"], "Age:", rec["age"], "Meds:", rec["active_medications"])

found = GLOBAL_PATIENT_REGISTRY.find_patient("प्रकाश देशमुख")
assert found is not None
assert found["name"] == "प्रकाश देशमुख"
print("Found patient in registry successfully!")

print("\n2. Testing follow-up session start...")
fu_sid = "test_fu_sess_02"
state_fu, greeting = GLOBAL_DIALOGUE_MANAGER.start_followup_session("प्रकाश देशमुख", fu_sid)
print("Follow-up branch:", state_fu.branch)
print("Current question:", state_fu.current_question_id)
print("Greeting:", greeting)
assert state_fu.branch == "follow_up"
assert state_fu.current_question_id == "FU_RECENT_SUGAR"
assert "प्रकाश देशमुख" in greeting
print("Follow-up session initialized successfully!")

print("\n3. Testing question selector for follow_up track...")
q_next = GLOBAL_QUESTION_SELECTOR.select_next_question(
    current_branch="follow_up",
    asked_question_ids=["FU_RECENT_SUGAR"],
    completed_topics=["consent", "demographics", "diabetic_status", "blood_sugar_readings"],
    questions_asked_count=1,
    demographics={"name": "प्रकाश देशमुख", "age": 54, "gender": "Male"},
    symptoms_reported=[],
    risk_signals=[],
    max_budget=8
)
print("Next Follow-up Question ID:", q_next["question_id"])
print("Question text (Hindi):", q_next["question_hi"])
assert q_next["branch"] == "follow_up"
print("Follow-up question selector verified successfully!")

print("\nALL FOLLOW-UP & PATIENT REGISTRY CHECKS PASSED!")
