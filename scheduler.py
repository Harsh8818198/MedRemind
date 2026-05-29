import os
import time
import threading
from datetime import datetime, timedelta
import re
from dotenv import load_dotenv

import storage
import voice
from agent import AdherenceAgent

# Load env configurations
load_dotenv(override=True)
RETRY_INTERVAL = int(os.getenv("RETRY_INTERVAL_MINUTES", "5"))

def parse_snooze_minutes(patient_text: str) -> int:
    """Extract snooze minutes from patient speech using regex. Fallback to 15 mins."""
    numbers = re.findall(r"\d+", patient_text)
    if numbers:
        minutes = int(numbers[0])
        # Cap snooze minutes between 1 and 60 for safety
        return max(1, min(60, minutes))
    
    # Text-based number fallback
    text_numbers = {
        "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, 
        "half": 30, "an hour": 60, "one hour": 60
    }
    for word, mins in text_numbers.items():
        if word in patient_text.lower():
            return mins
            
    return 15 # Default snooze duration

def calculate_future_time(minutes: int) -> str:
    """Calculate future time in HH:MM format."""
    now = datetime.now()
    future = now + timedelta(minutes=minutes)
    return future.strftime("%H:%M")

def run_reminder_call(reminder: dict, is_test: bool = False):
    """
    Stateful conversation loop running in an isolated thread.
    Initiates audio dialog with the patient, processes turns, and logs outcomes.
    """
    patient = reminder["patient"]
    medication = reminder["medication"]
    dosage = reminder["dosage"]
    reminder_id = reminder["id"]
    scheduled_time = reminder["time"]
    
    print(f"\n[ALERT] Starting medication reminder call for {patient} ({medication} {dosage})...")
    
    # Initialize the agent
    agent = AdherenceAgent(patient, medication, dosage)
    
    # Start call with introductory greeting
    speech = agent.start_call()
    voice.speak(speech)
    
    end_call = False
    outcome = "NO_RESPONSE"
    guardian_note = "Call initiated but patient did not respond."
    turns = 0
    max_turns = 5
    
    # Run interactive multi-turn call
    while not end_call and turns < max_turns:
        turns += 1
        
        # Listen for patient response (will fallback to typed input gracefully if text mode)
        patient_reply = voice.listen(reminder=reminder, last_agent_speech=speech)
        
        # Check for empty silence
        if not patient_reply:
            # Silence turn
            res = agent.process_turn("")
        else:
            res = agent.process_turn(patient_reply)
            
        speech = res.get("spoken_reply", "")
        outcome = res.get("outcome", "OTHER")
        end_call = res.get("end_call", False)
        guardian_note = res.get("guardian_note", "")
        
        # Speak back the agent's reply
        voice.speak(speech)
        
        # Handle silence or continuous retry logic
        if outcome == "NO_RESPONSE" and not patient_reply:
            break # Exit loop to trigger scheduler retry logic
            
    # If the turn cap is reached without explicit resolution, mark as other
    if turns >= max_turns and not end_call:
        outcome = "OTHER"
        guardian_note = f"Call reached max turns ({max_turns}) without completion. Guardian intervention suggested."
        
    print(f"\n[Call Ended] Classification Outcome: {outcome}")
    
    # Generate warm, plain-English summary of transcript
    print("Generating call summary for guardian...")
    summary = agent.generate_summary()
    
    # Handle Outcomes and update reminder state
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if outcome in ["TAKEN", "TAKEN_EARLIER"]:
        # Success state
        storage.update_reminder(reminder_id, {
            "last_run_date": today_str,
            "next_run": scheduled_time, # Reset next run to original schedule
            "retry_count": 0
        })
        print(f"[Success] Adherence logged. Guardian summary: {summary}")
        
    elif outcome in ["REFUSED", "CONFUSED", "MEDICAL_CONCERN", "OTHER"]:
        # Serious issue / Escalation state
        storage.update_reminder(reminder_id, {
            "last_run_date": today_str,
            "next_run": scheduled_time,
            "retry_count": 0
        })
        # Highlight alert to guardian
        color = "\033[91m" if outcome != "OTHER" else "\033[93m"
        print(f"\n[GUARDIAN ESCALATION - {outcome}] {guardian_note}")
        print(f"Summary: {summary}\n")
        
    elif outcome == "SNOOZE":
        # Snooze state - Reschedule for later today (does not set last_run_date)
        patient_text = " ".join([t["text"] for t in agent.transcript if t["role"] == "Patient"])
        snooze_mins = parse_snooze_minutes(patient_text)
        
        # For fast scheduler testing, use 30 seconds instead of actual minutes
        if is_test:
            snooze_mins = 1 # Quick 1 min snooze for manual testing
            
        future_time = calculate_future_time(snooze_mins)
        storage.update_reminder(reminder_id, {
            "next_run": future_time,
            "retry_count": 0
        })
        print(f"[Snooze] Patient requested snooze. Rescheduled call to {future_time} (in {snooze_mins} mins).")
        print(f"Guardian summary: {summary}")
        
    elif outcome == "NO_RESPONSE":
        # Retry logic
        retry_limit = 3
        current_retries = reminder.get("retry_count", 0)
        
        if current_retries < retry_limit:
            next_retry_count = current_retries + 1
            # In test mode, wait 1 minute for retry, else standard interval
            retry_mins = 1 if is_test else RETRY_INTERVAL
            future_time = calculate_future_time(retry_mins)
            
            storage.update_reminder(reminder_id, {
                "next_run": future_time,
                "retry_count": next_retry_count
            })
            print(f"[No Response] Retry {next_retry_count}/{retry_limit} scheduled at {future_time}.")
        else:
            # Escalated failure
            storage.update_reminder(reminder_id, {
                "last_run_date": today_str,
                "next_run": scheduled_time,
                "retry_count": 0
            })
            outcome = "NO_RESPONSE_FAILED"
            guardian_note = f"Call failed. No response from patient after {retry_limit} attempts."
            print(f"\n[GUARDIAN ALERT - NO RESPONSE] {guardian_note}")
            print(f"Please check on the patient immediately.\n")

    # Calculate average response latency and coherence score across all turns
    import json
    latencies = []
    coherences = []
    for h in agent.history:
        if h.get("role") == "assistant":
            try:
                data = json.loads(h.get("content", "{}"))
                if "response_latency_sec" in data:
                    latencies.append(data["response_latency_sec"])
                if "coherence_score" in data:
                    coherences.append(data["coherence_score"])
            except Exception:
                pass
    avg_latency = sum(latencies) / len(latencies) if latencies else None
    avg_coherence = sum(coherences) / len(coherences) if coherences else None

    # Predict adherence risk score
    try:
        from analytics import AdherencePredictor
        predictor = AdherencePredictor()
        predictor.train()
        risk_score = predictor.predict_risk(reminder)
    except Exception:
        risk_score = 0.15

    # Save to persistent logs
    storage.log_call(
        reminder_id=reminder_id,
        patient=patient,
        medication=medication,
        dosage=dosage,
        scheduled_time=scheduled_time,
        transcript=agent.transcript,
        outcome=outcome,
        guardian_note=guardian_note,
        summary=summary,
        response_latency_sec=avg_latency,
        coherence_score=avg_coherence,
        risk_score=risk_score,
        escalation_tier=0
    )

def poll_and_execute_scheduler(stop_event: threading.Event):
    """Main scheduler clock loop. Polls every 30 seconds for active, due reminders."""
    print("\n[Scheduler Active] MedRemind is monitoring reminders in the background...")
    print("Press Ctrl+C to stop.\n")
    
    while not stop_event.is_set():
        now = datetime.now()
        current_time_str = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        
        reminders = storage.load_reminders()
        
        for r in reminders:
            if not r.get("active", True):
                continue
                
            # A reminder is due if:
            # 1. next_run matches current_time
            # 2. it hasn't been successfully completed today (last_run_date != today_str) OR it's a retry/snooze (where next_run was calculated and last_run_date is blank/previous)
            if r["next_run"] == current_time_str and r["last_run_date"] != today_str:
                # Spawn threading instance to handle this call without stalling the scheduler
                call_thread = threading.Thread(
                    target=run_reminder_call, 
                    args=(r,),
                    daemon=True
                )
                call_thread.start()
                
                # Mark that we initiated execution so it doesn't fire multiple times in the same minute
                # We temporarily set last_run_date to "pending" until the thread completes or logs
                r["last_run_date"] = "pending"
                storage.save_reminders(reminders)
                
        # Wait 30 seconds before polling again
        time.sleep(30)
