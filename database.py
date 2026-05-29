import os
import sqlite3
import json
import uuid
from datetime import datetime

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(DATA_DIR, "medremind.db")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.jsonl")

def get_connection():
    """Create a thread-safe connection to the SQLite database with Row mapping."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite tables and apply migrations if JSON data is present."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Create Reminders table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        patient TEXT NOT NULL,
        medication TEXT NOT NULL,
        dosage TEXT NOT NULL,
        time TEXT NOT NULL,
        next_run TEXT NOT NULL,
        last_run_date TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        retry_count INTEGER DEFAULT 0
    )
    """)
    
    # 2. Create Logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        reminder_id TEXT,
        patient TEXT NOT NULL,
        medication TEXT NOT NULL,
        dosage TEXT NOT NULL,
        scheduled_time TEXT,
        outcome TEXT NOT NULL,
        guardian_note TEXT,
        summary TEXT,
        transcript TEXT,  -- Stored as JSON serialized string
        response_latency_sec REAL,
        coherence_score REAL,
        risk_score REAL,
        escalation_tier INTEGER DEFAULT 0
    )
    """)
    
    conn.commit()
    conn.close()
    
    # Run automatic JSON migration if legacy files exist
    migrate_to_sqlite()

def migrate_to_sqlite():
    """Migrate legacy JSON reminders and JSONL logs to SQLite, keeping backup files."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if we have reminders to migrate
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                reminders = json.load(f)
            
            print(f"[SQLite Migration] Found {len(reminders)} reminders in reminders.json. Migrating...")
            for r in reminders:
                cursor.execute("""
                INSERT OR IGNORE INTO reminders (id, patient, medication, dosage, time, next_run, last_run_date, active, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["id"],
                    r["patient"],
                    r["medication"],
                    r["dosage"],
                    r["time"],
                    r["next_run"],
                    r.get("last_run_date", ""),
                    1 if r.get("active", True) else 0,
                    r.get("retry_count", 0)
                ))
            conn.commit()
            
            # Backup old reminders file
            bak_path = REMINDERS_FILE + ".bak"
            if os.path.exists(bak_path):
                os.remove(bak_path)
            os.rename(REMINDERS_FILE, bak_path)
            print(f"[SQLite Migration] Successfully migrated reminders. Backed up to {bak_path}")
        except Exception as e:
            print(f"[SQLite Migration Error] Reminders migration failed: {e}")

    # Check if we have call logs to migrate
    if os.path.exists(LOGS_FILE):
        try:
            logs = []
            with open(LOGS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        logs.append(json.loads(line.strip()))
            
            print(f"[SQLite Migration] Found {len(logs)} logs in logs.jsonl. Migrating...")
            for log in logs:
                # Format transcript safely as JSON string
                transcript_str = json.dumps(log.get("transcript", []))
                
                cursor.execute("""
                INSERT INTO logs (timestamp, reminder_id, patient, medication, dosage, scheduled_time, outcome, guardian_note, summary, transcript, response_latency_sec, coherence_score, risk_score, escalation_tier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log.get("timestamp", datetime.now().isoformat()),
                    log.get("reminder_id"),
                    log.get("patient"),
                    log.get("medication"),
                    log.get("dosage"),
                    log.get("scheduled_time"),
                    log.get("outcome"),
                    log.get("guardian_note"),
                    log.get("summary"),
                    transcript_str,
                    log.get("response_latency_sec"),
                    log.get("coherence_score"),
                    log.get("risk_score"),
                    log.get("escalation_tier", 0)
                ))
            conn.commit()
            
            # Backup old logs file
            bak_path = LOGS_FILE + ".bak"
            if os.path.exists(bak_path):
                os.remove(bak_path)
            os.rename(LOGS_FILE, bak_path)
            print(f"[SQLite Migration] Successfully migrated logs. Backed up to {bak_path}")
        except Exception as e:
            print(f"[SQLite Migration Error] Logs migration failed: {e}")
            
    conn.close()

# --- BACKWARD-COMPATIBLE API REPLACEMENTS ---

def row_to_reminder(row) -> dict:
    """Helper to convert sqlite3.Row into a standard reminders dictionary."""
    if not row:
        return {}
    r = dict(row)
    r["active"] = bool(r["active"])
    return r

def row_to_log(row) -> dict:
    """Helper to convert sqlite3.Row into standard logs dictionary."""
    if not row:
        return {}
    l = dict(row)
    # Deserialize transcript safely
    if l.get("transcript"):
        try:
            l["transcript"] = json.loads(l["transcript"])
        except Exception:
            l["transcript"] = []
    else:
        l["transcript"] = []
    return l

def load_reminders() -> list[dict]:
    """Retrieve all reminders, matching old JSON structure."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return [row_to_reminder(row) for row in rows]

def save_reminders(reminders_list: list):
    """
    Overwrites the SQLite reminders table to maintain compat with JSON overrides.
    Warning: This is less efficient than fine-grained updates, but guarantees no breakage.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders")
    for r in reminders_list:
        cursor.execute("""
        INSERT INTO reminders (id, patient, medication, dosage, time, next_run, last_run_date, active, retry_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["id"],
            r["patient"],
            r["medication"],
            r["dosage"],
            r["time"],
            r["next_run"],
            r.get("last_run_date", ""),
            1 if r.get("active", True) else 0,
            r.get("retry_count", 0)
        ))
    conn.commit()
    conn.close()

def add_reminder(patient: str, medication: str, dosage: str, time_str: str) -> dict:
    """Add a new reminder to SQLite, matching storage.py signature."""
    # Validate time format
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        raise ValueError("Time must be in HH:MM format (24-hour clock)")

    new_id = str(uuid.uuid4())[:8]
    new_reminder = {
        "id": new_id,
        "patient": patient,
        "medication": medication,
        "dosage": dosage,
        "time": time_str,
        "next_run": time_str,
        "last_run_date": "",
        "active": True,
        "retry_count": 0
    }
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO reminders (id, patient, medication, dosage, time, next_run, last_run_date, active, retry_count)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        new_reminder["id"],
        new_reminder["patient"],
        new_reminder["medication"],
        new_reminder["dosage"],
        new_reminder["time"],
        new_reminder["next_run"],
        new_reminder["last_run_date"],
        1,
        0
    ))
    conn.commit()
    conn.close()
    return new_reminder

def delete_reminder(reminder_id: str) -> bool:
    """Delete reminder from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    changes = conn.total_changes
    conn.commit()
    conn.close()
    return changes > 0

def update_reminder(reminder_id: str, updates: dict) -> bool:
    """Perform optimized granular column updates on a reminder."""
    if not updates:
        return False
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # Formulate query dynamically
    fields = []
    values = []
    for k, v in updates.items():
        if k == "active":
            v = 1 if v else 0
        fields.append(f"{k} = ?")
        values.append(v)
        
    values.append(reminder_id)
    query = f"UPDATE reminders SET {', '.join(fields)} WHERE id = ?"
    
    cursor.execute(query, tuple(values))
    changes = conn.total_changes
    conn.commit()
    conn.close()
    return changes > 0

def log_call(reminder_id: str, patient: str, medication: str, dosage: str, 
             scheduled_time: str, transcript: list, outcome: str, 
             guardian_note: str, summary: str,
             response_latency_sec: float = None,
             coherence_score: float = None,
             risk_score: float = None,
             escalation_tier: int = 0):
    """Log a check-in call session to SQLite."""
    conn = get_connection()
    cursor = conn.cursor()
    
    transcript_str = json.dumps(transcript)
    timestamp_str = datetime.now().isoformat()
    
    cursor.execute("""
    INSERT INTO logs (timestamp, reminder_id, patient, medication, dosage, scheduled_time, outcome, guardian_note, summary, transcript, response_latency_sec, coherence_score, risk_score, escalation_tier)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp_str,
        reminder_id,
        patient,
        medication,
        dosage,
        scheduled_time,
        outcome,
        guardian_note,
        summary,
        transcript_str,
        response_latency_sec,
        coherence_score,
        risk_score,
        escalation_tier
    ))
    conn.commit()
    conn.close()

def load_logs() -> list[dict]:
    """Retrieve all call logs from SQLite database, sorted chronologically."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [row_to_log(row) for row in rows]
