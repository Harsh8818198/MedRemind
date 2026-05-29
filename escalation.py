import os
from dotenv import load_dotenv

# Load env configurations
load_dotenv(override=True)

# Try importing twilio helper
try:
    from twilio.rest import Client
    HAS_TWILIO = True
except ImportError:
    HAS_TWILIO = False

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()
CAREGIVER_PHONE = os.getenv("CAREGIVER_PHONE", "").strip()
EMERGENCY_PHONE = os.getenv("EMERGENCY_PHONE", "").strip()
ESCALATION_ENABLED = os.getenv("ESCALATION_ENABLED", "true").lower() == "true"

def send_twilio_sms(to_number: str, message_body: str) -> bool:
    """Send an SMS notification using Twilio API with graceful error handling."""
    if not ESCALATION_ENABLED:
        print("[Escalation] Alerting disabled via ESCALATION_ENABLED=false.")
        return False
        
    if not HAS_TWILIO:
        print("[Escalation Fallback] Twilio module not installed. Mock SMS logged to console.")
        return False
        
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, to_number]):
        print("[Escalation Fallback] Twilio credentials or phone numbers missing in .env. Mock SMS logged to console.")
        return False
        
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # Handle phone number formatting gently
        from_phone = TWILIO_FROM_NUMBER
        if not from_phone.startswith("+") and not from_phone.startswith("whatsapp:"):
            from_phone = f"+{from_phone}"
            
        dest_phone = to_number
        if not dest_phone.startswith("+") and not dest_phone.startswith("whatsapp:"):
            dest_phone = f"+{dest_phone}"
            
        message = client.messages.create(
            body=message_body,
            from_=from_phone,
            to=dest_phone
        )
        print(f"[Twilio SMS Sent] SID: {message.sid} to {to_number}")
        return True
    except Exception as e:
        print(f"[Twilio Error] Failed to send SMS: {e}")
        return False

def escalate(reminder: dict, outcome: str, transcript: list = None, custom_note: str = None) -> int:
    """
    4-Tier Emergency Escalation Matrix.
    Processes the check-in outcome and triggers real Twilio SMS alerts.
    Returns the escalation tier level (0-4) triggered.
    """
    patient = reminder.get("patient", "Patient")
    med = reminder.get("medication", "Medication")
    dosage = reminder.get("dosage", "")
    time_str = reminder.get("time", "12:00")
    
    # Compile deep link for caregiver to immediately dial
    deep_link = f"http://127.0.0.1:5000/?action=call&reminder_id={reminder.get('id', 'test')}"
    
    # ----------------------------------------------------
    # TIER 4: MEDICAL EMERGENCY (Immediate severe health threat)
    # ----------------------------------------------------
    if outcome == "MEDICAL_EMERGENCY":
        tier = 4
        sms_body = (
            f"[CRITICAL EMERGENCY] MedRemind detected a severe crisis for {patient} during their {time_str} "
            f"check-in for {med} {dosage}.\n"
            f"Patient reported severe distress: '{custom_note or 'Chest pain / Difficulty breathing / Falling'}'\n"
            f"Please check on them immediately! Call Link: {deep_link}"
        )
        print(f"\n[TIER 4 ESCALATION - URGENT MEDICAL EMERGENCY]")
        print(f"SMS Content: {sms_body}\n")
        
        # Dispatch to caregiver AND emergency contact
        send_twilio_sms(CAREGIVER_PHONE, sms_body)
        if EMERGENCY_PHONE:
            send_twilio_sms(EMERGENCY_PHONE, sms_body)
            
        return tier

    # ----------------------------------------------------
    # TIER 3: CRITICAL ISSUES (Persistent refusal, disorientation, or illness complaints)
    # ----------------------------------------------------
    if outcome in ["REFUSED", "CONFUSED", "MEDICAL_CONCERN", "NO_RESPONSE_FAILED"]:
        tier = 3
        reason_map = {
            "REFUSED": "Patient actively refused taking the dose.",
            "CONFUSED": "Patient exhibited disorientation or confusion.",
            "MEDICAL_CONCERN": f"Patient complained of feeling unwell: '{custom_note or 'No details'}'",
            "NO_RESPONSE_FAILED": "Patient did not respond to any call attempts today."
        }
        reason_text = reason_map.get(outcome, "Patient did not successfully take their dose.")
        
        sms_body = (
            f"[MedRemind Alert] Call escalation for {patient} regarding their {time_str} dose of {med} {dosage}.\n"
            f"Status: {outcome} - {reason_text}\n"
            f"Please coordinate care. Call caregiver dashboard: {deep_link}"
        )
        print(f"\n[TIER 3 ESCALATION - CRITICAL ADHERENCE FAILURE]")
        print(f"SMS Content: {sms_body}\n")
        
        # Dispatch to caregiver
        send_twilio_sms(CAREGIVER_PHONE, sms_body)
        return tier

    # ----------------------------------------------------
    # TIER 2: REFUSAL INTERVENTION (Persuasion state)
    # ----------------------------------------------------
    # Refusal outcomes are logged, but trigger Tier 3 only if they persist
    # ----------------------------------------------------
    
    # ----------------------------------------------------
    # TIER 1: MISSED CALL / SILENCE (Scheduled for automatic retry)
    # ----------------------------------------------------
    if outcome == "NO_RESPONSE":
        print(f"[Tier 1 Escalation] Missed call for {patient}. Automatic retry scheduled in background.")
        return 1
        
    return 0
