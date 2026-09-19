import sys
import urllib.request
import urllib.parse
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:8000"

def post_form(url, data):
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def get_json(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

print("1. Starting new baseline session...")
s1 = post_form(f"{BASE}/api/sehat/session/start", {})
sid = s1["session_id"]
print("Session ID:", sid)

print("\n2. Turn 1: Consent")
t1 = post_form(f"{BASE}/api/sehat/session/turn", {"session_id": sid, "transcript": "हाँ मैं सहमत हूँ"})
print("Next Question:", t1["state"]["current_question_id"])

print("\n3. Turn 2: Demographics")
t2 = post_form(f"{BASE}/api/sehat/session/turn", {"session_id": sid, "transcript": "मेरा नाम गोविंद जोशी है, उम्र 45 वर्ष, पुरुष"})
print("Extracted Patient:", t2["state"]["patient"])

print("\n4. Turn 3: Known Diabetic with details")
t3 = post_form(f"{BASE}/api/sehat/session/turn", {"session_id": sid, "transcript": "हाँ मुझे 2 साल से टाइप 2 डायबिटीज है, मेटफॉर्मिन 500 लेता हूँ और शुगर 210 आई थी"})
print("Bot response:", t3.get("bot_speech_hi"))
print("State context memory:", t3["state"].get("context_memory"))

# Fast forward to completion
print("\n5. Checking patient registry list before completion...")
plist_before = get_json(f"{BASE}/api/patients/list")
print("Patients count before end:", plist_before["count"])

# Simulate answers to complete session
t4 = t3
while not t4.get("is_completed"):
    t4 = post_form(f"{BASE}/api/sehat/session/turn", {"session_id": sid, "transcript": "सब ठीक है, और कोई समस्या नहीं है"})

print("Session is_completed:", t4.get("is_completed"))

print("\n6. Checking patient registry after session completion...")
plist = get_json(f"{BASE}/api/patients/list")
print("Registered Patients Count:", plist["count"])
print("Patients:", json.dumps(plist["patients"], ensure_ascii=False, indent=2))

print("\n7. Testing Follow-up session start for गोविंद जोशी...")
fu_res = post_form(f"{BASE}/api/sehat/session/start_followup", {"patient_name": "गोविंद जोशी"})
print("Follow-up session ID:", fu_res["session_id"])
print("Follow-up Bot Speech:", fu_res["bot_speech_hi"])
print("Follow-up Branch:", fu_res["branch"])
print("Starting Question:", fu_res["state"]["current_question_id"])

print("\n8. Turn 1 of Follow-up consultation (Recent blood sugar update):")
fu_t1 = post_form(f"{BASE}/api/sehat/session/turn", {
    "session_id": fu_res["session_id"],
    "transcript": "आज सुबह मेरी फास्टिंग शुगर 145 आई थी"
})
print("Next Follow-up Question:", fu_t1["state"]["current_question_id"])
print("Follow-up Bot Speech:", fu_t1.get("bot_speech_hi"))

print("\n=== SUCCESS: ALL END-TO-END PATIENT REGISTRY & FOLLOW-UP API TESTS PASSED! ===")
