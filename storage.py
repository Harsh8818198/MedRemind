import os
import threading
import database

# Maintain original file variables for diagnostic imports or folder structure checks
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.jsonl")

# Thread lock to maintain reentrant capability in memory if external modules look for it
_storage_lock = threading.RLock()

def init_storage():
    """Ensure the SQLite database is initialized and data migration is completed."""
    with _storage_lock:
        database.init_db()

def load_reminders() -> list:
    """Load reminders from the SQLite database."""
    init_storage()
    with _storage_lock:
        return database.load_reminders()

def save_reminders(reminders: list):
    """Save/overwrite reminders in the SQLite database."""
    init_storage()
    with _storage_lock:
        database.save_reminders(reminders)

def add_reminder(patient: str, medication: str, dosage: str, time_str: str) -> dict:
    """Add a reminder to SQLite database."""
    init_storage()
    with _storage_lock:
        return database.add_reminder(patient, medication, dosage, time_str)

def delete_reminder(reminder_id: str) -> bool:
    """Delete a reminder by ID in SQLite database."""
    init_storage()
    with _storage_lock:
        return database.delete_reminder(reminder_id)

def update_reminder(reminder_id: str, updates: dict) -> bool:
    """Update specific fields of a reminder in SQLite database."""
    init_storage()
    with _storage_lock:
        return database.update_reminder(reminder_id, updates)

def log_call(reminder_id: str, patient: str, medication: str, dosage: str, 
             scheduled_time: str, transcript: list, outcome: str, 
             guardian_note: str, summary: str,
             response_latency_sec: float = None,
             coherence_score: float = None,
             risk_score: float = None,
             escalation_tier: int = 0):
    """Append a full summary log to the SQLite database."""
    init_storage()
    with _storage_lock:
        database.log_call(
            reminder_id=reminder_id,
            patient=patient,
            medication=medication,
            dosage=dosage,
            scheduled_time=scheduled_time,
            transcript=transcript,
            outcome=outcome,
            guardian_note=guardian_note,
            summary=summary,
            response_latency_sec=response_latency_sec,
            coherence_score=coherence_score,
            risk_score=risk_score,
            escalation_tier=escalation_tier
        )

def load_logs() -> list:
    """Load all call logs from the SQLite database."""
    init_storage()
    with _storage_lock:
        return database.load_logs()
