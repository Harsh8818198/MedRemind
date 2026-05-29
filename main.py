import os
import sys
import argparse
import threading
from datetime import datetime
from dotenv import load_dotenv

# Add relative imports
import storage
import voice
import scheduler
from agent import HAS_KEYS, MODEL_NAME, API_PROVIDER

BANNER = r"""\033[95m
  __  __          _ _____                    _           _ 
 |  \/  |        | |  __ \                  (_)         | |
 | \  / | ___  __| | |__) |___ _ __ ___  _   _ _ __   __| |
 | |\/| |/ _ \/ _` |  _  // _ \ '_ ` _ \| | | | '_ \ / _` |
 | |  | |  __/ (_| | | \ \  __/ | | | | | |_| | | | | (_| |
 |_|  |_|\___|\__,_|_|  \_\___|_| |_| |_|\__,_|_| |_|\__,_|
\033[0m
     State-of-the-Art AI Caregiver Med Adherence System
"""

def print_banner():
    print(BANNER)
    # Print API connection status for diagnostic support
    if HAS_KEYS:
        print(f"[Connected] API provider: \033[1m{API_PROVIDER.upper()}\033[0m | Model: \033[36m{MODEL_NAME}\033[0m")
    else:
        print("[Offline / Mock Mode] No API Keys loaded. Simulating conversation logic locally.")
    print(f"[Interface Mode] Interaction Channel: \033[35m{voice.VOICE_MODE.upper()}\033[0m")
    print("-" * 75)


def handle_add():
    """Interactively add a new medication reminder."""
    print("\n[Add New Medication Reminder]")
    
    # 1. Patient Name
    default_patient = os.getenv("PATIENT_NAME", "Grandpa")
    patient = input(f"Patient Name (default '{default_patient}'): ").strip()
    if not patient:
        patient = default_patient
        
    # 2. Medication Name
    medication = input("Medication Name (e.g. Metformin, Lisinopril): ").strip()
    while not medication:
        medication = input("\033[91mMedication Name is required:\033[0m ").strip()
        
    # 3. Dosage
    dosage = input("Dosage (e.g. 500mg, 1 tablet): ").strip()
    while not dosage:
        dosage = input("\033[91mDosage is required:\033[0m ").strip()
        
    # 4. Reminder Time
    time_str = input("Scheduled Time (24h format HH:MM, e.g. 08:30, 20:00): ").strip()
    while True:
        try:
            datetime.strptime(time_str, "%H:%M")
            break
        except ValueError:
            time_str = input("\033[91mInvalid format. Please enter time as HH:MM (24-hour clock):\033[0m ").strip()
            
    # Add to database
    try:
        new_reminder = storage.add_reminder(patient, medication, dosage, time_str)
        print(f"\n[Success] Added reminder! ID: \033[1m{new_reminder['id']}\033[0m")
        print(f"   Patient: {patient} | Pill: {medication} ({dosage}) | Time: {time_str}")
    except Exception as e:
        print(f"\033[91m[Error] Failed to add reminder: {e}\033[0m")

def handle_list():
    """List all active medication reminders in a neat formatted table."""
    reminders = storage.load_reminders()
    print("\n[Medication Reminders Schedule]")
    
    if not reminders:
        print("No reminders found. Use 'python main.py add' to create one.")
        return
        
    print(f"{'ID':<10} | {'Patient':<12} | {'Medication':<18} | {'Dosage':<12} | {'Time':<6} | {'Next Run':<8} | {'Status':<8}")
    print("-" * 85)
    for r in reminders:
        status = "Active" if r.get("active", True) else "Disabled"
        print(f"{r['id']:<10} | {r['patient']:<12} | {r['medication']:<18} | {r['dosage']:<12} | {r['time']:<6} | {r['next_run']:<8} | {status:<8}")
    print()

def handle_delete(reminder_id: str):
    """Delete a reminder by ID."""
    if storage.delete_reminder(reminder_id):
        print(f"[Success] Deleted reminder ID \033[1m{reminder_id}\033[0m")
    else:
        print(f"[Error] Reminder ID \033[1m{reminder_id}\033[0m not found.")

def handle_test():
    """Instantly trigger a simulated reminder call to test the agent, voice/text channels, and parsing."""
    print("\n[Interactive Test Check-In]")
    reminders = storage.load_reminders()
    
    selected_reminder = None
    if reminders:
        print("Select an existing reminder to test, or press Enter to run a mock reminder:")
        for idx, r in enumerate(reminders):
            print(f" [{idx + 1}] {r['patient']} - {r['medication']} ({r['dosage']})")
        
        choice = input("Choice (number or Enter): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(reminders):
            selected_reminder = reminders[int(choice) - 1]
            
    if not selected_reminder:
        # Generate generic mock reminder
        selected_reminder = {
            "id": "test-id",
            "patient": os.getenv("PATIENT_NAME", "Grandpa"),
            "medication": "Aspirin",
            "dosage": "75mg",
            "time": "12:00",
            "next_run": "12:00",
            "last_run_date": "",
            "retry_count": 0
        }
        print(f"\nStarting mock test call for {selected_reminder['patient']} - {selected_reminder['medication']} ({selected_reminder['dosage']})...")
    
    # Run call synchronously in main thread for easy testing
    scheduler.run_reminder_call(selected_reminder, is_test=True)

def handle_start():
    """Start the background scheduler process."""
    print_banner()
    
    # Validate there is at least one reminder
    reminders = storage.load_reminders()
    if not reminders:
        print("[Warning] You have no reminders scheduled. The scheduler will run but won't check anything.")
        print("   Use 'python main.py add' in another terminal window to set up reminders.\n")
        
    stop_event = threading.Event()
    scheduler_thread = threading.Thread(
        target=scheduler.poll_and_execute_scheduler, 
        args=(stop_event,), 
        daemon=True
    )
    scheduler_thread.start()
    
    try:
        # Keep main thread alive
        while True:
            scheduler_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\nStopping MedRemind scheduler...")
        stop_event.set()
        scheduler_thread.join()
        print("Goodbye!")

def handle_logs(full_transcript: bool):
    """View historical logs and transcripts."""
    logs = storage.load_logs()
    print("\n[Historical Activity Logs]")
    
    if not logs:
        print("No calls recorded yet.")
        return
        
    print(f"Total Call Sessions Checked: {len(logs)}")
    
    # Calculate statistics
    outcomes = {}
    for entry in logs:
        out = entry.get("outcome", "UNKNOWN")
        outcomes[out] = outcomes.get(out, 0) + 1
        
    print("Outcome Statistics:")
    for out, count in outcomes.items():
        color = "\033[92m" if "TAKEN" in out else "\033[91m" if "CONCERN" in out or "FAILED" in out or "REFUSED" in out else "\033[93m"
        print(f" - {color}{out:<18}\033[0m: {count} times")
        
    print("-" * 75)
    
    # List each call
    for idx, log in enumerate(reversed(logs)):
        print(f"\n[{idx + 1}] Date/Time  : {log['timestamp'][:16].replace('T', ' ')}")
        print(f"    Patient    : {log['patient']} | Pill: {log['medication']} ({log['dosage']})")
        print(f"    Outcome    : {log['outcome']}")
        print(f"    Summary    : {log['summary']}")
        
        if full_transcript:
            print("    Transcript :")
            for msg in log.get("transcript", []):
                role_col = "\033[94m" if msg["role"] == "Agent" else "\033[32m"
                print(f"      {role_col}{msg['role']}\033[0m: {msg['text']}")
        print("-" * 50)

def main():
    parser = argparse.ArgumentParser(description="MedRemind - State-of-the-Art AI Medication Adherence CLI Companion")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Subcommands
    subparsers.add_parser("add", help="Interactively add a new medication reminder")
    subparsers.add_parser("list", help="List all scheduled reminders")
    
    del_parser = subparsers.add_parser("delete", help="Delete a scheduled reminder")
    del_parser.add_argument("id", help="The 8-character ID of the reminder to delete")
    
    subparsers.add_parser("test", help="Instantly launch a test check-in call (mock/existing)")
    subparsers.add_parser("start", help="Start the live background clock & scheduler")
    
    logs_parser = subparsers.add_parser("logs", help="Display all past caregiver transcripts & outcomes")
    logs_parser.add_argument("--full", action="store_true", help="Print complete dialog transcripts of past calls")
    
    args = parser.parse_args()
    
    # Default behavior if no command passed: show help
    if not args.command:
        print_banner()
        parser.print_help()
        print("\nExample Quick Start:")
        print("  python main.py add        # Set up a new reminder")
        print("  python main.py test       # Try out the AI conversation right now!")
        print("  python main.py start      # Run the background scheduler loop")
        sys.exit(0)
        
    if args.command == "add":
        handle_add()
    elif args.command == "list":
        handle_list()
    elif args.command == "delete":
        handle_delete(args.id)
    elif args.command == "test":
        print_banner()
        handle_test()
    elif args.command == "start":
        handle_start()
    elif args.command == "logs":
        handle_logs(args.full)

if __name__ == "__main__":
    main()
