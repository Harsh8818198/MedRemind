import os
import sys
from dotenv import load_dotenv

# Load env configurations
load_dotenv()
VOICE_MODE = os.getenv("VOICE_MODE", "text").strip().lower()

# Advanced fallbacks for pyttsx3 and speech_recognition
TTS_AVAILABLE = False
STT_AVAILABLE = False
tts_engine = None

if VOICE_MODE == "voice":
    # Try importing pyttsx3
    try:
        import pyttsx3
        # Initialize text-to-speech engine
        try:
            tts_engine = pyttsx3.init()
            # Set rate to be slower and clearer for elderly (~120 - 130 words per minute)
            tts_engine.setProperty("rate", 125)
            # Set volume (0.0 to 1.0)
            tts_engine.setProperty("volume", 0.9)
            
            # Select voice (prefer female or soft voice if available, typically index 1 on Windows)
            voices = tts_engine.getProperty("voices")
            if len(voices) > 1:
                tts_engine.setProperty("voice", voices[1].id)
            elif len(voices) > 0:
                tts_engine.setProperty("voice", voices[0].id)
                
            TTS_AVAILABLE = True
        except Exception as e:
            print(f"\n[Voice System Alert] Failed to initialize TTS engine: {e}")
            print("Running in Text-Only output fallback mode.\n")
    except ImportError:
        print("\n[Voice System Alert] pyttsx3 not installed.")
        print("Running in Text-Only output fallback mode.\n")

    # Try importing SpeechRecognition
    try:
        import speech_recognition as sr
        STT_AVAILABLE = True
    except ImportError:
        print("[Voice System Alert] speech_recognition (SpeechRecognition) not installed.")
        print("Running in Text-Only input fallback mode.\n")

def speak(text: str):
    """Speak text using TTS if available; always print to the screen in a beautiful format."""
    # Print styled terminal output
    print(f"\n[Agent]: {text}")
    sys.stdout.flush()
    
    if VOICE_MODE == "voice" and TTS_AVAILABLE and tts_engine:
        try:
            # We run in a separate try-except block so TTS failures don't halt execution
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as tts_err:
            # Print error but continue running program
            pass

def listen(timeout_sec: int = 6, reminder: dict = None, last_agent_speech: str = "") -> str:
    """
    Listen to speech from the mic and return transcription.
    Falls back to terminal text input if VOICE_MODE is 'text', 
    if STT is unavailable, or if microphone initialization fails.
    If run in a background thread, automatically simulates a realistic patient response to prevent blocking.
    """
    import threading
    is_background = (threading.current_thread() != threading.main_thread())
    
    if is_background:
        print("[Background Run] Simulating patient response automatically...")
        from agent import generate_patient_reply
        p_name = reminder["patient"] if reminder else "Grandpa"
        med = reminder["medication"] if reminder else "Aspirin"
        dos = reminder["dosage"] if reminder else "75mg"
        
        reply = generate_patient_reply(p_name, med, dos, last_agent_speech)
        print(f"[Simulated Patient Reply]: {reply}")
        return reply

    if VOICE_MODE != "voice" or not STT_AVAILABLE:
        return _get_text_input()
        
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    
    # Adjust for ambient noise and listen
    try:
        with sr.Microphone() as source:
            print("\n[Listening... Speak now]")
            sys.stdout.flush()
            
            # Adjust for 1 second of noise to calibrate thresholds
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            
            # Record audio
            audio = recognizer.listen(source, timeout=timeout_sec, phrase_time_limit=10)
            
        print("[Processing speech...]")
        sys.stdout.flush()
        
        # Transcribe using Google Web Speech API (free and requires no API key)
        phrase = recognizer.recognize_google(audio)
        print(f"[Patient Voice]: {phrase}")
        return phrase
        
    except sr.WaitTimeoutError:
        print("[Silence detected]")
        return ""
    except sr.UnknownValueError:
        print("[Could not understand audio]")
        return ""
    except sr.RequestError as e:
        print(f"[Speech recognition service error: {e}]")
        print("Switching automatically to console input fallback.")
        return _get_text_input()
    except Exception as mic_err:
        print(f"\n[Microphone error: {mic_err}]")
        print("You may need to grant microphone access, install PyAudio, or check your settings.")
        print("Switching automatically to console input fallback.")
        return _get_text_input()

def _get_text_input() -> str:
    """Helper to retrieve console text input from patient."""
    try:
        user_input = input("\n[Patient Input (Type reply)]: ")
        return user_input.strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCall disconnected.")
        sys.exit(0)
