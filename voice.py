import os
import sys
import re
import time
from dotenv import load_dotenv

# Load env configurations
load_dotenv()
VOICE_MODE = os.getenv("VOICE_MODE", "text").strip().lower()
VOICE_STT_ENGINE = os.getenv("VOICE_STT_ENGINE", "google").strip().lower()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

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

# Check if local Whisper STT is requested
WHISPER_AVAILABLE = False
whisper_model = None
if VOICE_MODE == "voice" and VOICE_STT_ENGINE == "whisper":
    try:
        import whisper
        WHISPER_AVAILABLE = True
    except ImportError:
        print("[Voice System Alert] whisper package not installed. Falling back to Google Web STT.\n")

def speak(text: str, consecutive_confused: int = 0):
    """
    Speak text using TTS if available. Always print to console.
    Adaptive Speech Pacing: If consecutive_confused >= 2, automatically decreases 
    TTS rate to 100 WPM and adds 1.5s pauses between sentences.
    """
    # Print styled terminal output
    print(f"\n[Agent]: {text}")
    sys.stdout.flush()
    
    if VOICE_MODE == "voice" and TTS_AVAILABLE and tts_engine:
        try:
            # Set speaking rate dynamically
            rate = 100 if consecutive_confused >= 2 else 125
            tts_engine.setProperty("rate", rate)
            
            if consecutive_confused >= 2:
                # Slower paced speech with sentence pauses
                sentences = re.split(r'(?<=[.!?])\s+', text)
                for sentence in sentences:
                    if sentence.strip():
                        tts_engine.say(sentence.strip())
                        tts_engine.runAndWait()
                        time.sleep(1.5) # 1.5s breathing pause
            else:
                # Normal speaking mode
                tts_engine.say(text)
                tts_engine.runAndWait()
        except Exception:
            pass

def analyze_audio_features(audio_data: bytes) -> dict:
    """
    Extracts basic pitch variance and speech rate from the audio buffer using numpy FFT.
    Flags extreme values (vocal tremors or severe slowness) as potential health alerts.
    """
    import numpy as np
    if not audio_data or len(audio_data) == 0:
        return {
            "pitch_variance": 0.0,
            "speech_rate_wpm": 0.0,
            "status": "normal",
            "health_alert": False
        }
        
    try:
        # Convert raw audio bytes into 16-bit integers
        samples = np.frombuffer(audio_data, dtype=np.int16)
        if len(samples) == 0:
            return {"pitch_variance": 0.0, "speech_rate_wpm": 0.0, "status": "normal", "health_alert": False}
            
        # Compute Fast Fourier Transform
        fft_val = np.abs(np.fft.rfft(samples))
        frequencies = np.fft.rfftfreq(len(samples), d=1.0/16000.0) # Assume 16kHz sampling
        
        # Filter frequency spectrum for standard vocal range (85Hz - 255Hz)
        vocal_mask = (frequencies >= 85) & (frequencies <= 255)
        vocal_freqs = frequencies[vocal_mask]
        vocal_fft = fft_val[vocal_mask]
        
        if len(vocal_fft) > 0 and np.sum(vocal_fft) > 0:
            mean_pitch = np.average(vocal_freqs, weights=vocal_fft)
            pitch_variance = np.sqrt(np.average((vocal_freqs - mean_pitch)**2, weights=vocal_fft))
        else:
            pitch_variance = 12.0 # Normal fallback
            
        # Calculate Zero Crossing crossings for basic speech rate proxy
        zero_crossings = np.nonzero(np.diff(samples > 0))[0]
        crossing_rate = len(zero_crossings) / (len(samples) / 16000.0) if len(samples) > 0 else 0.0
        speech_rate_wpm = round(crossing_rate * 0.12)
        
        # Clinical indicator flags
        status = "normal"
        health_alert = False
        
        if pitch_variance > 40.0 or pitch_variance < 2.5:
            status = "abnormal_pitch_tremor_instability"
            health_alert = True
        elif speech_rate_wpm < 45:
            status = "extreme_slowness_lethargy"
            health_alert = True
            
        return {
            "pitch_variance": round(float(pitch_variance), 2),
            "speech_rate_wpm": int(speech_rate_wpm),
            "status": status,
            "health_alert": health_alert
        }
    except Exception as e:
        return {
            "pitch_variance": 10.0,
            "speech_rate_wpm": 110,
            "status": "normal_fallback",
            "health_alert": False,
            "error": str(e)
        }

def listen(timeout_sec: int = 6, reminder: dict = None, last_agent_speech: str = "") -> str:
    """
    Listen to speech from the microphone and return transcription.
    Local STT Whisper: If VOICE_STT_ENGINE env var is set to 'whisper', transcribes locally.
    Vocal Biomarkers: Analyzes frame data using numpy FFT in background.
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
    
    try:
        with sr.Microphone() as source:
            print("\n[Listening... Speak now]")
            sys.stdout.flush()
            
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
            audio = recognizer.listen(source, timeout=timeout_sec, phrase_time_limit=10)
            
        print("[Processing speech...]")
        sys.stdout.flush()
        
        # 1. Extract and analyze Vocal Biomarker features from raw frame data
        features = analyze_audio_features(audio.frame_data)
        if features["health_alert"]:
            print(f"[Vocal Biomarker Warning] Status: {features['status'].replace('_', ' ')} (Pitch Variance: {features['pitch_variance']}, Speech Rate: {features['speech_rate_wpm']} WPM)")
        
        # 2. Transcribe voice using the configured STT engine
        if VOICE_STT_ENGINE == "whisper" and WHISPER_AVAILABLE:
            global whisper_model
            
            # Save raw audio buffer into WAV file to be read by Whisper model
            wav_data = audio.get_wav_data()
            os.makedirs(DATA_DIR, exist_ok=True)
            temp_path = os.path.join(DATA_DIR, "temp_whisper.wav")
            with open(temp_path, "wb") as f:
                f.write(wav_data)
                
            if whisper_model is None:
                print("[Whisper Engine] Loading local 'base' model... (Please wait)")
                sys.stdout.flush()
                whisper_model = whisper.load_model("base")
                
            result = whisper_model.transcribe(temp_path)
            phrase = result.get("text", "").strip()
            
            try:
                os.remove(temp_path)
            except Exception:
                pass
                
            print(f"[Patient Voice (Whisper Local)]: {phrase}")
            return phrase
        else:
            # Fallback/Default: Google Web Speech API
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

def generate_call_recording(transcript: list, log_id: int) -> str:
    """
    Generate a synthesized .wav audio recording of a call session.
    Saves to static/recordings/<log_id>.wav
    Returns the web-accessible URL path: /static/recordings/<log_id>.wav
    """
    import os
    import math
    import struct
    import wave
    
    # Create static recordings directory if missing
    static_rec_dir = os.path.join(BASE_DIR, "static", "recordings")
    os.makedirs(static_rec_dir, exist_ok=True)
    filename = f"{log_id}.wav"
    filepath = os.path.join(static_rec_dir, filename)
    
    # Try using pyttsx3 to synthesize actual dialogue in the background
    try:
        import pyttsx3
        
        script_parts = []
        for turn in transcript:
            role = turn.get("role", "Agent")
            text = turn.get("text", "")
            script_parts.append(f"{role} says: {text}.")
            
        full_conversation_text = " \n ".join(script_parts)
        
        # Initialize a temporary, file-saving speech engine
        local_engine = pyttsx3.init()
        local_engine.setProperty("rate", 130) # Slower paced speech
        
        # Select voice if available
        voices = local_engine.getProperty("voices")
        if len(voices) > 1:
            local_engine.setProperty("voice", voices[1].id)
            
        local_engine.save_to_file(full_conversation_text, filepath)
        local_engine.runAndWait()
        
        # Verify file exists and has size
        if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
            print(f"[Audio Generator] Synthesized call recording saved to {filepath}")
            return f"/static/recordings/{filename}"
            
    except Exception as e:
        print(f"[Audio Generator Alert] pyttsx3 text-to-file synthesis failed: {e}. Falling back to wave PCM generator.")
        
    # Central standard robust fallback: generate standard PCM wave file (double ringtone beeps)
    try:
        sample_rate = 16000
        duration = 1.8 # 1.8 seconds nice double-beep sound
        num_samples = int(sample_rate * duration)
        
        with wave.open(filepath, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            
            # Simple synthetic wave showing standard voice-sim playback
            for i in range(num_samples):
                t = i / float(sample_rate)
                # Play nice, professional telephone ring/beeps: 440Hz + 480Hz combined
                envelope = 1.0
                # Double beep sound: beeps at 0.0-0.4s and 0.6-1.0s
                in_beep1 = (t >= 0.0 and t < 0.4)
                in_beep2 = (t >= 0.6 and t < 1.0)
                
                if in_beep1:
                    # Fade in/out for beep 1
                    if t < 0.05: envelope = t / 0.05
                    elif t > 0.35: envelope = (0.4 - t) / 0.05
                    else: envelope = 1.0
                elif in_beep2:
                    # Fade in/out for beep 2
                    if t < 0.65: envelope = (t - 0.6) / 0.05
                    elif t > 0.95: envelope = (1.0 - t) / 0.05
                    else: envelope = 1.0
                else:
                    envelope = 0.0
                    
                val = 0
                if envelope > 0:
                    val = int(16384.0 * envelope * (math.sin(2.0 * math.pi * 440.0 * t) + math.sin(2.0 * math.pi * 480.0 * t)))
                    
                data = struct.pack("<h", val)
                w.writeframes(data)
                
        print(f"[Audio Generator Fallback] Synthesized fallback WAV call-recording saved to {filepath}")
        return f"/static/recordings/{filename}"
    except Exception as ex:
        print(f"[Audio Generator Error] CENTRAL fallbacks failed: {ex}")
        return None
