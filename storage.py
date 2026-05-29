import os
import json
import uuid
from datetime import datetime

# Define storage directory inside medremind folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.jsonl")

def init_storage():
    """Ensure the data directory and standard storage files exist."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    
    if not os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)

def load_reminders() -> list:
    """Load all medication reminders from storage."""
    init_storage()
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading reminders: {e}")
        return []

def save_reminders(reminders: list):
    """Save all medication reminders to storage."""
    init_storage()
    try:
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=4)
    except Exception as e:
        print(f"Error saving reminders: {e}")

def add_reminder(patient: str, medication: str, dosage: str, time_str: str) -> dict:
    """
    Add a new reminder to the scheduler database.
    time_str must be in format "HH:MM" (24h).
    """
    init_storage()
    reminders = load_reminders()
    
    # Validate time format
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        raise ValueError("Time must be in HH:MM format (24-hour clock)")

    new_reminder = {
        "id": str(uuid.uuid4())[:8],
        "patient": patient,
        "medication": medication,
        "dosage": dosage,
        "time": time_str,          # Original scheduled time
        "next_run": time_str,      # Next execution time (updates on snooze/reschedule)
        "last_run_date": "",       # Date (YYYY-MM-DD) when it was last run
        "active": True,
        "retry_count": 0
    }
    
    reminders.append(new_reminder)
    save_reminders(reminders)
    return new_reminder

def delete_reminder(reminder_id: str) -> bool:
    """Delete a reminder by its ID."""
    reminders = load_reminders()
    initial_len = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]
    
    if len(reminders) < initial_len:
        save_reminders(reminders)
        return True
    return False

def update_reminder(reminder_id: str, updates: dict) -> bool:
    """Update specific fields of a reminder."""
    reminders = load_reminders()
    for r in reminders:
        if r["id"] == reminder_id:
            r.update(updates)
            save_reminders(reminders)
            return True
    return False

def log_call(reminder_id: str, patient: str, medication: str, dosage: str, 
             scheduled_time: str, transcript: list, outcome: str, 
             guardian_note: str, summary: str):
    """Append a full summary log of the completed call to logs.jsonl."""
    init_storage()
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "reminder_id": reminder_id,
        "patient": patient,
        "medication": medication,
        "dosage": dosage,
        "scheduled_time": scheduled_time,
        "outcome": outcome,
        "guardian_note": guardian_note,
        "summary": summary,
        "transcript": transcript  # List of dicts: {"role": "Agent"/"Patient", "text": "..."}
    }
    
    try:
        with open(LOGS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Error writing to log file: {e}")

def load_logs() -> list:
    """Load all call logs from logs.jsonl."""
    init_storage()
    if not os.path.exists(LOGS_FILE):
        return []
    
    logs = []
    try:
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line.strip()))
    except Exception as e:
        print(f"Error loading logs: {e}")
    return logs
