import os
import sys
import uuid
import datetime
from flask import Flask, jsonify, request, render_template, send_from_directory
from dotenv import load_dotenv

# Add imports
import storage
import voice
import scheduler
import threading
from agent import AdherenceAgent, HAS_KEYS, MODEL_NAME, API_PROVIDER

load_dotenv(override=True)

# Initialize Flask app
# Since our templates and static folders are inside medremind, we set absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

# Active interactive call sessions memory store
# Maps session_id -> { "agent": AdherenceAgent, "reminder": dict, "turns": int, "last_activity": datetime }
active_sessions = {}

def cleanup_sessions():
    """Remove inactive/abandoned simulation sessions older than 10 minutes (600 seconds)."""
    now = datetime.datetime.now()
    expired_ids = []
    for sid, sess in list(active_sessions.items()):
        last_act = sess.get("last_activity", now)
        if (now - last_act).total_seconds() > 600:
            expired_ids.append(sid)
    for sid in expired_ids:
        del active_sessions[sid]

@app.route("/")
def home():
    """Serve the caregiver dashboard SPA page."""
    return render_template("index.html")

@app.route("/api/status", methods=["GET"])
def get_status():
    """Retrieve detailed system and engine status diagnostics."""
    scheduler_active = bool(scheduler_thread and scheduler_thread.is_alive())
    
    return jsonify({
        "status": "success",
        "scheduler_active": scheduler_active,
        "api_connected": HAS_KEYS,
        "api_provider": API_PROVIDER,
        "model_name": MODEL_NAME,
        "tally_online": False,
        "reminders_count": len(storage.load_reminders()),
        "logs_count": len(storage.load_logs())
    })

# REST API - Reminders CRUD

@app.route("/api/reminders", methods=["GET"])
def get_reminders():
    """Retrieve all scheduled medication reminders."""
    reminders = storage.load_reminders()
    return jsonify(reminders)

@app.route("/api/reminders", methods=["POST"])
def add_reminder():
    """Add a new medication reminder to the schedule."""
    data = request.json
    if not data or not all(k in data for k in ["patient", "medication", "dosage", "time"]):
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
    try:
        new_reminder = storage.add_reminder(
            patient=data["patient"],
            medication=data["medication"],
            dosage=data["dosage"],
            time_str=data["time"]
        )
        return jsonify({"status": "success", "reminder": new_reminder})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/api/reminders/<reminder_id>", methods=["DELETE"])
def delete_reminder(reminder_id):
    """Delete a medication reminder from the schedule."""
    if storage.delete_reminder(reminder_id):
        return jsonify({"status": "success", "message": f"Deleted reminder {reminder_id}"})
    return jsonify({"status": "error", "message": "Reminder ID not found"}), 404

# REST API - Logs & Historical audits

@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Retrieve historical check-in logs and adherence metrics."""
    logs = storage.load_logs()
    
    # Compile adherence statistics
    total_calls = len(logs)
    outcomes = {}
    adherence_success = 0
    
    for log in logs:
        out = log.get("outcome", "UNKNOWN")
        outcomes[out] = outcomes.get(out, 0) + 1
        if out in ["TAKEN", "TAKEN_EARLIER"]:
            adherence_success += 1
            
    adherence_rate = round((adherence_success / total_calls) * 100) if total_calls > 0 else 0
    
    return jsonify({
        "logs": list(reversed(logs)), # Most recent first
        "metrics": {
            "total_calls": total_calls,
            "adherence_rate": adherence_rate,
            "outcomes": outcomes
        }
    })

# REST API - Interactive Real-Time Call Simulator

@app.route("/api/simulate/start", methods=["POST"])
def start_simulation():
    """Initiate a stateful check-in session for a specific reminder."""
    cleanup_sessions()
    data = request.json
    if not data or "reminder_id" not in data:
        return jsonify({"status": "error", "message": "Missing reminder ID"}), 400
        
    reminder_id = data["reminder_id"]
    reminders = storage.load_reminders()
    reminder = next((r for r in reminders if r["id"] == reminder_id), None)
    
    # If not found, use a mock reminder for testing
    if not reminder:
        reminder = {
            "id": "mock-test",
            "patient": os.getenv("PATIENT_NAME", "Grandpa"),
            "medication": "Aspirin",
            "dosage": "75mg",
            "time": "12:00"
        }
        
    # Instantiate the stateful Agent
    agent = AdherenceAgent(
        patient_name=reminder["patient"],
        medication=reminder["medication"],
        dosage=reminder["dosage"]
    )
    
    # Get the opening greeting statement
    greeting = agent.start_call()
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    active_sessions[session_id] = {
        "agent": agent,
        "reminder": reminder,
        "turns": 0,
        "last_activity": datetime.datetime.now()
    }
    
    return jsonify({
        "status": "success",
        "session_id": session_id,
        "greeting": greeting,
        "patient": reminder["patient"],
        "medication": reminder["medication"],
        "dosage": reminder["dosage"]
    })

@app.route("/api/simulate/turn", methods=["POST"])
def process_simulation_turn():
    """Process a single dialogue turn input from the patient."""
    cleanup_sessions()
    data = request.json
    if not data or not all(k in data for k in ["session_id", "patient_reply"]):
        return jsonify({"status": "error", "message": "Missing required turn parameters"}), 400
        
    session_id = data["session_id"]
    reply = data["patient_reply"].strip()
    
    if session_id not in active_sessions:
        return jsonify({"status": "error", "message": "Call session expired or invalid"}), 404
        
    session = active_sessions[session_id]
    agent = session["agent"]
    last_act = session.get("last_activity")
    if last_act:
        latency_sec = round((datetime.datetime.now() - last_act).total_seconds(), 1)
    else:
        latency_sec = 3.5
    session["last_activity"] = datetime.datetime.now()
    
    # Process turn with Gemini LLM (or rules engine fallback if no key)
    res = agent.process_turn(reply, latency_sec)
    session["turns"] += 1
    
    # Force end if turn cap is reached
    if session["turns"] >= 5:
        res["end_call"] = True
        res["outcome"] = "OTHER"
        res["guardian_note"] = "Simulation reached maximum turns limit."
        
    return jsonify({
        "status": "success",
        "spoken_reply": res["spoken_reply"],
        "outcome": res["outcome"],
        "end_call": res["end_call"],
        "guardian_note": res["guardian_note"]
    })

@app.route("/api/simulate/end", methods=["POST"])
def end_simulation():
    """Generate final summary and write call session to log files."""
    cleanup_sessions()
    data = request.json
    if not data or not all(k in data for k in ["session_id", "outcome", "guardian_note"]):
        return jsonify({"status": "error", "message": "Missing outcome data"}), 400
        
    session_id = data["session_id"]
    outcome = data["outcome"]
    guardian_note = data["guardian_note"]
    
    if session_id not in active_sessions:
        return jsonify({"status": "error", "message": "Call session expired or invalid"}), 404
        
    session = active_sessions[session_id]
    agent = session["agent"]
    reminder = session["reminder"]
    reminder_id = reminder["id"]
    scheduled_time = reminder.get("time", "12:00")
    
    # Generate final empathetic plain-English summary for caregiver logs
    summary = agent.generate_summary()
    
    # Update reminder status on schedule if it's a real reminder
    if reminder_id != "mock-test":
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        if outcome in ["TAKEN", "TAKEN_EARLIER"]:
            storage.update_reminder(reminder_id, {
                "last_run_date": today_str,
                "next_run": scheduled_time,
                "retry_count": 0
            })
        elif outcome in ["REFUSED", "CONFUSED", "MEDICAL_CONCERN", "OTHER"]:
            storage.update_reminder(reminder_id, {
                "last_run_date": today_str,
                "next_run": scheduled_time,
                "retry_count": 0
            })
        elif outcome == "SNOOZE":
            patient_text = " ".join([t["text"] for t in agent.transcript if t["role"] == "Patient"])
            snooze_mins = scheduler.parse_snooze_minutes(patient_text)
            future = datetime.datetime.now() + datetime.timedelta(minutes=snooze_mins)
            future_time = future.strftime("%H:%M")
            
            storage.update_reminder(reminder_id, {
                "next_run": future_time,
                "retry_count": 0
            })
        elif outcome == "NO_RESPONSE":
            retry_limit = 3
            current_retries = reminder.get("retry_count", 0)
            
            if current_retries < retry_limit:
                next_retry_count = current_retries + 1
                retry_mins = int(os.getenv("RETRY_INTERVAL_MINUTES", "5"))
                future = datetime.datetime.now() + datetime.timedelta(minutes=retry_mins)
                future_time = future.strftime("%H:%M")
                
                storage.update_reminder(reminder_id, {
                    "next_run": future_time,
                    "retry_count": next_retry_count
                })
            else:
                # Escalated failure
                storage.update_reminder(reminder_id, {
                    "last_run_date": today_str,
                    "next_run": scheduled_time,
                    "retry_count": 0
                })
                outcome = "NO_RESPONSE_FAILED"
                guardian_note = f"Call failed. No response from patient after {retry_limit} attempts."
            
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

    # Persist log entry
    storage.log_call(
        reminder_id=reminder_id,
        patient=reminder["patient"],
        medication=reminder["medication"],
        dosage=reminder["dosage"],
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
    
    # Clean memory store
    if session_id in active_sessions:
        del active_sessions[session_id]
    
    return jsonify({
        "status": "success",
        "summary": summary,
        "outcome": outcome,
        "guardian_note": guardian_note
    })

# Global stop event and thread references
stop_event = threading.Event()
scheduler_thread = None

def main():
    global scheduler_thread
    # Make templates and static dirs exist
    os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)
    
    # Spawn background scheduler thread automatically!
    scheduler_thread = threading.Thread(
        target=scheduler.poll_and_execute_scheduler,
        args=(stop_event,),
        daemon=True
    )
    scheduler_thread.start()
    
    print("\n===========================================================================")
    print("             MedRemind Caregiver Portal Server")
    print("===========================================================================")
    print(f"Hosting dashboard at: \033[92mhttp://127.0.0.1:5000\033[0m")
    if HAS_KEYS:
        print(f"API Connected | Model: {MODEL_NAME} | Provider: {API_PROVIDER.upper()}")
    else:
        print("Offline Mock Mode Active")
    print("Background Medication Scheduler Clock: \033[92mACTIVE (Polling 30s)\033[0m")
    print("===========================================================================\n")
    
    app.run(host="127.0.0.1", port=5000, debug=False)

if __name__ == "__main__":
    main()
