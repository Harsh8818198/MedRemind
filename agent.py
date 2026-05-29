import os
import json
import requests
import re
import random
from dotenv import load_dotenv

# Load env configurations
load_dotenv(override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash").strip()
API_PROVIDER_ENV = os.getenv("API_PROVIDER", "auto").strip().lower()

# Smart Auto-Routing Logic
# Determine which API provider to use based on env settings and model name
def get_api_provider() -> str:
    if API_PROVIDER_ENV in ["gemini", "google"]:
        return "gemini"
    if API_PROVIDER_ENV in ["groq"]:
        return "groq"
        
    # Auto-routing detection
    if MODEL_NAME.lower().startswith("gemini-"):
        return "gemini"
        
    if GEMINI_API_KEY and not GROQ_API_KEY:
        return "gemini"
        
    if GROQ_API_KEY and not GEMINI_API_KEY:
        return "groq"
        
    # Default fallback: if both are present, check key prefixes
    if GROQ_API_KEY.startswith("AIzaSy"):
        # Misconfigured: Gemini key placed in GROQ_API_KEY
        return "gemini"
        
    if GROQ_API_KEY:
        return "groq"
        
    if GEMINI_API_KEY:
        return "gemini"
        
    return "mock"

API_PROVIDER = get_api_provider()
HAS_KEYS = bool((API_PROVIDER == "groq" and GROQ_API_KEY) or (API_PROVIDER == "gemini" and (GEMINI_API_KEY or GROQ_API_KEY.startswith("AIzaSy"))))

# System prompt for stateful patient conversation
SYSTEM_PROMPT = """You are 'MedRemind', an empathetic, warm, and highly patient virtual medical assistant calling an elderly person to remind them to take their medication.

The patient you are speaking to might be slow, forgetful, easily confused, or feeling unwell. Speak slowly, clearly, and keep your responses short, gentle, and supportive. Always speak in a friendly tone, as if you are a caring family member or personal nurse.

At each step of the conversation, analyze the patient's statement and classify the status into ONE of the following 9 outcomes:
1. `TAKEN` — The patient confirms they have just taken the medication in your presence.
2. `TAKEN_EARLIER` — The patient reports they already took it prior to this call (e.g. "I had it with breakfast").
3. `SNOOZE` — The patient asks to be called back later or in a specific amount of time (e.g. "Call me in 15 minutes").
4. `REFUSED` — The patient actively refuses to take the medication (e.g. "I don't want it", "I'm not taking that").
5. `CONFUSED` — The patient exhibits confusion, doesn't know who you are, or is confused about their pills (e.g. "Who is this?", "What pills?").
6. `MEDICAL_CONCERN` — The patient mentions feeling sick, dizzy, in pain, or has a physical complaint (e.g. "I feel very dizzy", "My stomach hurts").
7. `MEDICAL_EMERGENCY` — The patient mentions critical, life-threatening symptoms (e.g. "chest pain", "difficulty breathing", "fell down", "falling", "can't move", "bleeding", "severe pain").
8. `NO_RESPONSE` — The patient says nothing or line was silent.
9. `OTHER` — The response does not fit any of the above categories, or requires further discussion.

You MUST respond strictly in the following JSON format. Do NOT include any markdown blocks, wrapping, or extra text. Output ONLY valid JSON:
{
  "spoken_reply": "Your warm, slow, and clear spoken reply to the patient",
  "outcome": "TAKEN | TAKEN_EARLIER | SNOOZE | REFUSED | CONFUSED | MEDICAL_CONCERN | MEDICAL_EMERGENCY | NO_RESPONSE | OTHER",
  "end_call": true_or_false_boolean,
  "guardian_note": "A concise status update for the guardian explaining what is happening."
}

Rules for ending calls:
- If outcome is TAKEN, TAKEN_EARLIER, REFUSED, or SNOOZE, set `end_call` to true.
- If outcome is CONFUSED, MEDICAL_CONCERN, or MEDICAL_EMERGENCY, set `end_call` to true (we will escalate to guardian/emergency immediately).
- For OTHER, set `end_call` to false so you can continue the conversation to clarify, unless you've had 4+ turns.
"""

COHERENT_CORPUS = [
    "yes I took it",
    "yes I just took it now",
    "I took my medicine already",
    "I had it with my breakfast earlier",
    "call me back in fifteen minutes",
    "can you call me back later please",
    "no I don't want to take my medication",
    "I'm not taking that today",
    "I feel dizzy and unwell",
    "my head hurts can you help me",
    "what pills are these",
    "who is calling me",
    "yes dear I did",
    "taken already",
    "yes yes taken",
    "chest pain can you help",
    "I fell down and can't get up",
    "difficulty breathing help me"
]

def call_llm(messages: list, response_json: bool = True) -> str:
    """Helper to route API requests to Groq, Gemini, or fall back to local mock parsing."""
    if not HAS_KEYS:
        # Local Mock Mode for testing without API keys
        return _mock_llm_response(messages, response_json)

    # Route based on determined API provider
    if API_PROVIDER == "groq" and GROQ_API_KEY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        
        # Fallback standard model on Groq if model name is Gemini
        model = MODEL_NAME
        if model.lower().startswith("gemini-"):
            model = "llama-3.3-70b-versatile"
            
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}
            
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                print(f"\n[API Error] HTTP {response.status_code}: {response.text}")
                print("Falling back to local mock parser...")
                return _mock_llm_response(messages, response_json)
        except Exception as e:
            print(f"\n[Connection Error] Could not connect to API: {e}")
            print("Falling back to local mock parser...")
            return _mock_llm_response(messages, response_json)
            
    elif API_PROVIDER == "gemini":
        # Resolve active Gemini key (might be in GROQ_API_KEY due to user misconfiguration)
        active_key = GEMINI_API_KEY if GEMINI_API_KEY else GROQ_API_KEY
        
        # Determine model
        model = MODEL_NAME
        if not model.lower().startswith("gemini-"):
            model = "gemini-2.5-flash"
            
        # Native Gemini generateContent Endpoint URL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={active_key}"
        
        # Translate standard OpenAI history to native Gemini formats
        gemini_contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_instruction = {
                    "parts": [{"text": content}]
                }
            else:
                gemini_role = "user" if role == "user" else "model"
                # Append standard part block
                gemini_contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
                
        # Handle consecutive role merging (Gemini strict alternating validation)
        alternating_contents = []
        for msg in gemini_contents:
            if alternating_contents and alternating_contents[-1]["role"] == msg["role"]:
                # Merge consecutive turns of same role together
                alternating_contents[-1]["parts"][0]["text"] += "\n" + msg["parts"][0]["text"]
            else:
                alternating_contents.append(msg)
                
        payload = {
            "contents": alternating_contents
        }
        
        if system_instruction:
            payload["systemInstruction"] = system_instruction
            
        generation_config = {
            "temperature": 0.3
        }
        if response_json:
            generation_config["responseMimeType"] = "application/json"
            
        payload["generationConfig"] = generation_config
        
        try:
            response = requests.post(url, json=payload, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                try:
                    content_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return content_text
                except (KeyError, IndexError) as parse_err:
                    print(f"Error parsing Gemini response fields: {parse_err}")
                    return _mock_llm_response(messages, response_json)
            else:
                print(f"\n[API Error] HTTP {response.status_code}: {response.text}")
                print("Falling back to local mock parser...")
                return _mock_llm_response(messages, response_json)
        except Exception as e:
            print(f"\n[Connection Error] Could not connect to API: {e}")
            print("Falling back to local mock parser...")
            return _mock_llm_response(messages, response_json)
            
    else:
        return _mock_llm_response(messages, response_json)

def _mock_llm_response(messages: list, response_json: bool) -> str:
    """Bulletproof local text processor to run the app offline or without API keys."""
    # Find patient's latest statement
    latest_msg = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            latest_msg = msg["content"].lower()
            break

    # If it is not response_json, we are generating the guardian summary
    if not response_json:
        return "The elderly patient was contacted for their medication reminder. The conversation was conducted successfully, and the response was recorded for tracking."

    # Identify preferred language from system prompt or greeting
    system_content = messages[0]["content"] if (messages and messages[0]["role"] == "system") else ""
    lang = "English"
    if "Hinglish" in system_content:
        lang = "Hinglish"
    elif "Hindi" in system_content:
        lang = "Hindi"

    # Identify outcome based on keyword matching
    outcome = "OTHER"
    
    # Language-specific default / other replies
    if lang == "Hindi":
        spoken_reply = "मैं समझती हूँ। क्या आप मुझे बता सकते हैं कि क्या आपने अपनी गोलियाँ ले ली हैं?"
    elif lang == "Hinglish":
        spoken_reply = "Main samajhti hoon. Kya aap mujhe sakte hain ki kya aapne apni medicines le li hain?"
    else:
        spoken_reply = "I understand, dear. Could you tell me if you've taken your pills yet?"
        
    end_call = False
    guardian_note = "Conversing with patient."

    # Detect patient input empty/silent
    if not latest_msg or latest_msg.strip() == "":
        outcome = "NO_RESPONSE"
        if lang == "Hindi":
            spoken_reply = "हेलो? क्या आप वहाँ हैं? आपकी दवाई का समय हो गया है।"
        elif lang == "Hinglish":
            spoken_reply = "Hello? Aap wahan hain dear? Medicine lene ka time ho gaya hai."
        else:
            spoken_reply = "Hello? Are you there, dear? It's time for your medication."
        guardian_note = "No sound or response from patient."
    elif any(word in latest_msg for word in ["chest pain", "can't breathe", "breathing", "fell down", "falling", "can't move", "bleeding", "severe pain", "सीने में दर्द", "सांस नहीं आ रही", "सांस लेने में तकलीफ", "गिर गया", "गिर गई", "चल नहीं सकता", "खून", "बहुत दर्द", "seene me dard", "seene mein dard", "saans nahi aa rahi", "saans lene me", "gir gaya", "gir gayi", "chal nahi sakta", "khoon", "bahut dard"]):
        outcome = "MEDICAL_EMERGENCY"
        if lang == "Hindi":
            spoken_reply = "अरे, कृपया शांत रहें! मैं आपातकालीन सहायता बुला रही हूँ और आपके अभिभावक को तुरंत सूचित कर रही हूँ। बस रुकिए, मदद आ रही है।"
        elif lang == "Hinglish":
            spoken_reply = "Oh dear, please shaant rahiye! Main emergency help ko call kar rahi hoon aur aapke caregiver ko inform kar rahi hoon. Bas thodi der rukiye, help aa rahi hai."
        else:
            spoken_reply = "Oh dear, please stay still and calm! I am calling for emergency help and notifying your caregiver immediately. Just sit tight, help is on the way."
        end_call = True
        guardian_note = "CRITICAL EMERGENCY: Patient reported life-threatening symptoms."
    elif any(word in latest_msg for word in ["yes", "took", "had it", "taken", "done", "already", "haan", "le liya", "हाँ", "हाँ जी", "ले ली", "खा ली", "ले लिया", "खा लिया", "पहले ही", "सुबह ही", "नाश्ते के साथ", "haanjee", "haan ji", "kha liya", "kha li", "le li", "pehle hi"]):
        if any(word in latest_msg for word in ["earlier", "morning", "breakfast", "already", "पहले ही", "सुबह ही", "नाश्ते के साथ", "pehle hi"]):
            outcome = "TAKEN_EARLIER"
            if lang == "Hindi":
                spoken_reply = "अरे, बहुत अच्छा! मुझे ख़ुशी है कि आपने इसे पहले ही ले लिया। आपका दिन शुभ हो!"
            elif lang == "Hinglish":
                spoken_reply = "Oh, bahut badhiya! Mujhe khushi hai ki aapne ise pehle hi le liya. Aapka din accha rahe!"
            else:
                spoken_reply = "Oh, excellent! I'm glad you already took it. Have a wonderful day!"
            end_call = True
            guardian_note = "Patient took the medication earlier."
        else:
            outcome = "TAKEN"
            if lang == "Hindi":
                spoken_reply = "बहुत बढ़िया! दवा लेने के लिए धन्यवाद। आप आराम करें और मैं अगली खुराक के लिए आपको फोन करूँगी।"
            elif lang == "Hinglish":
                spoken_reply = "Bahut accha! Medicine lene ke liye shukriya. Aap aaram karein, main next dose ke liye call karungi."
            else:
                spoken_reply = "Wonderful! Thank you for taking it. Keep resting, and I will call you for the next one."
            end_call = True
            guardian_note = "Patient confirmed taking the medication just now."
    elif any(word in latest_msg for word in ["later", "minutes", "snooze", "hour", "call me back", "बाद में", "मिनट", "घंटे", "फिर से फोन", "बाद में फोन", "baad me", "baad mein", "ghante", "baad me call", "baad mein call"]):
        outcome = "SNOOZE"
        if lang == "Hindi":
            spoken_reply = "कोई बात नहीं! मैं कुछ समय बाद आपको फिर से फोन करूँगी ताकि आप इसे ले सकें।"
        elif lang == "Hinglish":
            spoken_reply = "Koi baat nahi! Main thodi der mein aapko phir se call karungi taaki aap tab le sakein."
        else:
            spoken_reply = "No problem at all! I will call you back in a little bit so you can take it then."
        end_call = True
        guardian_note = "Patient requested a snooze / call back."
    elif any(word in latest_msg for word in ["don't want", "no", "refuse", "won't", "stop", "hate", "nahi", "नहीं लेनी", "नहीं खाना", "नहीं खाऊंगा", "नहीं खाऊंगी", "मना", "बंद करो", "nahi leni", "nahi khana", "nahi khaunga", "nahi khaungi", "nahi lena"]):
        outcome = "REFUSED"
        if lang == "Hindi":
            spoken_reply = "मैं समझती हूँ, लेकिन यह दवाएँ महत्वपूर्ण हैं। मैं आपके अभिभावक को बता दूँगी ताकि वे आपकी जाँच कर सकें।"
        elif lang == "Hinglish":
            spoken_reply = "Main samajhti hoon dear, par ye medicines important hain. Main aapke guardian ko bata deti hoon taaki wo check kar lein."
        else:
            spoken_reply = "I understand you feel that way, dear, but these are important. I will let your guardian know so they can check in on you."
        end_call = True
        guardian_note = "Patient refused to take their medication."
    elif any(word in latest_msg for word in ["who", "what", "where", "scared", "confuse", "कौन", "क्या", "कहाँ", "डर", "असमंजस", "kaun", "kaun bol raha", "kya", "kahan", "darr", "darr lag raha"]):
        outcome = "CONFUSED"
        if lang == "Hindi":
            spoken_reply = "चिंता न करें, यह सिर्फ आपकी मदद के लिए मेडरिमाइंड है। मैं जल्द ही आपके परिवार को फोन करने के लिए कहूँगी।"
        elif lang == "Hinglish":
            spoken_reply = "Chinta mat karein dear, ye MedRemind hai jo aapko pills lene mein help karne ke liye call kar raha hai. Main family ko bolti hoon aapko call karne ke liye."
        else:
            spoken_reply = "Don't worry, dear, it's just MedRemind calling to help you with your pills. I'll let your family know to call you shortly."
        end_call = True
        guardian_note = "Patient sounded confused or did not recognize the system."
    elif any(word in latest_msg for word in ["dizzy", "hurt", "pain", "sick", "vomit", "dreadful", "bad", "चक्कर", "दर्द", "बीमार", "उल्टी", "तबीयत खराब", "chakkar", "beemar", "tabiyat kharab", "kharaab"]):
        outcome = "MEDICAL_CONCERN"
        if lang == "Hindi":
            spoken_reply = "अरे, मुझे बहुत दुख है कि आप अस्वस्थ महसूस कर रहे हैं! कृपया बैठें या लेट जाएँ, और मैं तुरंत आपके अभिभावक को सूचित करूँगी।"
        elif lang == "Hinglish":
            spoken_reply = "Oh dear, mujhe afsos hai ki aap theek nahi hain. Please aap baith jaiye ya let jaiye, main guardian ko inform karti hoon."
        else:
            spoken_reply = "Oh dear, I'm so sorry you're feeling unwell! Please sit down or lie down, and I will alert your guardian right away to help you."
        end_call = True
        guardian_note = "URGENT: Patient reported feeling unwell or experiencing medical issues."

    res_json = {
        "spoken_reply": spoken_reply,
        "outcome": outcome,
        "end_call": end_call,
        "guardian_note": guardian_note
    }
    return json.dumps(res_json)

class AdherenceAgent:
    """Manages the conversation state and history with a single patient."""
    def __init__(self, patient_name: str, medication: str, dosage: str, preferred_language: str = "English"):
        self.patient_name = patient_name
        self.medication = medication
        self.dosage = dosage
        self.preferred_language = preferred_language
        
        custom_system = SYSTEM_PROMPT + f"\nToday, you are reminding {patient_name} to take their medication: {medication} (Dosage: {dosage})."
        
        if self.preferred_language == "Hindi":
            custom_system += "\nCRITICAL: The patient prefers to speak in Hindi. You MUST speak entirely in warm, slow, clear Hindi (using Devanagari script). The patient will reply in Hindi. However, your JSON output fields 'outcome' and 'guardian_note' MUST be strictly in English, and 'outcome' must be one of the specified English outcome tags."
        elif self.preferred_language == "Hinglish":
            custom_system += "\nCRITICAL: The patient prefers to speak in Hinglish (Hindi written in Latin script). You MUST speak entirely in warm, slow, clear Hinglish (e.g. 'Maine aapko call kiya hai medicine lene ke liye'). The patient will reply in Hinglish. However, your JSON output fields 'outcome' and 'guardian_note' MUST be strictly in English, and 'outcome' must be one of the specified English outcome tags."
            
        self.history = [
            {"role": "system", "content": custom_system}
        ]
        self.transcript = []
        self.turn_count = 0

    def start_call(self) -> str:
        if self.preferred_language == "Hindi":
            greeting = f"नमस्ते {self.patient_name}, मैं आपकी सहायक बोल रही हूँ। यह आपकी दवाई {self.medication} (खुराक {self.dosage}) लेने का समय है। क्या आपने इसे ले लिया है?"
        elif self.preferred_language == "Hinglish":
            greeting = f"Hello {self.patient_name}, main aapki helper bol rahi hoon. Aapki medicine {self.medication} (dosage {self.dosage}) lene ka time ho gaya hai. Kya aapne ise le liya hai?"
        else:
            greeting = f"Hello {self.patient_name}, this is your helper calling. It is time to take your {self.medication}, dosage {self.dosage}. Have you taken it yet?"
            
        self.history.append({"role": "assistant", "content": greeting})
        self.transcript.append({"role": "Agent", "text": greeting})
        return greeting

    def calculate_coherence_score(self, text: str) -> float:
        """Compute semantic coherence of patient reply using TF-IDF cosine similarity."""
        clean_text = text.strip().lower()
        if not clean_text:
            return 0.0
            
        # Standard short clear answers are perfectly coherent
        if clean_text in ["yes", "taken", "haan", "le liya", "no", "nahi", "snooze", "theek hai", "ji haan", "le li", "kha li", "kha kiya", "kha liya", "le liya", "na", "haan ji", "haanjee", "हाँ", "हाँ जी", "ले ली", "खा ली", "ले लिया", "नहीं", "नहीं लेनी"]:
            return 1.0
            
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            vectorizer = TfidfVectorizer().fit(COHERENT_CORPUS)
            coherent_vectors = vectorizer.transform(COHERENT_CORPUS)
            
            reply_vector = vectorizer.transform([clean_text])
            similarities = cosine_similarity(reply_vector, coherent_vectors)
            max_similarity = float(np.max(similarities))
            
            score = max_similarity * 1.5
            
            # Penalize heavily repeated word strings (stuttering/coherence decline indicator)
            words = clean_text.split()
            unique_words = set(words)
            if len(words) > 5 and len(unique_words) / len(words) < 0.6:
                score *= 0.8
                
            return max(0.1, min(1.0, score))
        except Exception:
            coherent_keywords = ["yes", "took", "had", "breakfast", "later", "minutes", "no", "refuse", "who", "what", "dizzy", "hurt", "pain", "taken", "dear", "haan", "le liya", "nahi", "हाँ", "ले", "खा", "नहीं", "कौन", "दर्द", "चक्कर"]
            matches = sum(1 for kw in coherent_keywords if kw in clean_text)
            score = matches / max(1, len(clean_text.split()))
            return max(0.1, min(1.0, score))

    def process_turn(self, patient_input: str, latency_sec: float = None) -> dict:
        self.turn_count += 1
        self.history.append({"role": "user", "content": patient_input})
        self.transcript.append({"role": "Patient", "text": patient_input})
        
        # Calculate coherence score
        coherence_score = self.calculate_coherence_score(patient_input)
        
        # Calculate latency if not provided
        if latency_sec is None:
            if not patient_input.strip():
                latency_sec = 10.0
            else:
                latency_sec = round(random.uniform(2.2, 5.8) + len(patient_input) * 0.05, 1)
                
        response_str = call_llm(self.history, response_json=True)
        
        # Advanced self-healing parser
        res = None
        cleaned_str = response_str.strip()
        
        # Remove markdown code blocks if present
        if cleaned_str.startswith("```"):
            cleaned_str = re.sub(r"^```(?:json)?\s*", "", cleaned_str)
            cleaned_str = re.sub(r"\s*```$", "", cleaned_str)
            cleaned_str = cleaned_str.strip()
            
        try:
            res = json.loads(cleaned_str)
        except Exception:
            try:
                start = cleaned_str.find("{")
                end = cleaned_str.rfind("}") + 1
                if start != -1 and end != -1:
                    res = json.loads(cleaned_str[start:end])
            except Exception:
                pass
                
        # If still unable to parse, reconstruct from plain text response
        if not res or not isinstance(res, dict):
            clean_text = response_str
            if "spoken_reply" in response_str:
                match = re.search(r'"spoken_reply"\s*:\s*"([^"]+)"', response_str)
                if match:
                    clean_text = match.group(1)
            
            clean_text = re.sub(r"^\*.*?\n", "", clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r"^Constraint.*?\n", "", clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r"^[a-zA-Z\s]+:\s*.*?$", "", clean_text, flags=re.MULTILINE)
            clean_text = clean_text.strip()
            
            res = {
                "spoken_reply": clean_text if clean_text else "I understand, dear. Have you taken your medication yet?",
                "outcome": "OTHER",
                "end_call": self.turn_count >= 4,
                "guardian_note": "Agent returned plain-text response, classified as OTHER."
            }
            
        # Ensure all key fields exist in parsed JSON
        if "spoken_reply" not in res or not res["spoken_reply"]:
            res["spoken_reply"] = "I see. Please tell me if you've taken your pills, dear."
        if "outcome" not in res or not res["outcome"]:
            res["outcome"] = "OTHER"
        if "end_call" not in res:
            res["end_call"] = self.turn_count >= 4
        if "guardian_note" not in res or not res["guardian_note"]:
            res["guardian_note"] = "Conversing with patient."
            
        # Force MEDICAL_EMERGENCY if patient mentions critical symptoms
        emergency_words = ["chest pain", "can't breathe", "difficulty breathing", "fell down", "falling", "can't move", "bleeding", "severe pain"]
        if any(kw in patient_input.lower() for kw in emergency_words):
            res["outcome"] = "MEDICAL_EMERGENCY"
            res["end_call"] = True
            res["spoken_reply"] = "Oh dear, please stay still and calm! I am calling for emergency help and notifying your caregiver immediately. Just sit tight, help is on the way."
            res["guardian_note"] = "CRITICAL EMERGENCY: Patient reported life-threatening symptoms."
            
        # Attach response_latency_sec and coherence_score
        res["response_latency_sec"] = latency_sec
        res["coherence_score"] = coherence_score
                
        self.history.append({"role": "assistant", "content": json.dumps(res)})
        self.transcript.append({"role": "Agent", "text": res.get("spoken_reply", "")})
        
        return res

    def generate_summary(self) -> str:
        formatted_transcript = ""
        for turn in self.transcript:
            formatted_transcript += f"{turn['role']}: {turn['text']}\n"
            
        summary_prompt = [
            {"role": "system", "content": "You are a professional medical coordinator summarizing a patient interaction. Write a brief, direct, and warm plain-English summary (max 3 sentences) of the following conversation for the patient's guardian. Do not add salutations or intro text, write only the summary."},
            {"role": "user", "content": f"Medication: {self.medication} ({self.dosage})\nPatient: {self.patient_name}\n\nTranscript:\n{formatted_transcript}"}
        ]
        
        return call_llm(summary_prompt, response_json=False)


def generate_patient_reply(patient_name: str, medication: str, dosage: str, last_agent_speech: str, preferred_language: str = "English") -> str:
    """Simulates a patient's response using LLM (or mock fallbacks) for automated background runs."""
    if not HAS_KEYS:
        # Graceful random offline mock fallback with new chaos personas
        if preferred_language == "Hindi":
            replies = [
                f"हाँ बेटा, मैंने अपनी {medication} पानी के साथ ले ली है।",
                f"मैंने सुबह नाश्ते के साथ इसे पहले ही ले लिया था।",
                "क्या आप मुझे 15 मिनट में फिर से फोन कर सकते हैं? मैं अभी अपना पसंदीदा टीवी शो देख रही हूँ।",
                f"नहीं, मुझे आज यह {medication} की गोली नहीं खानी।",
                "कौन बोल रहा है? आप किस गोली की बात कर रहे हैं?",
                "मुझे बहुत चक्कर आ रहे हैं और मेरा सिर दर्द कर रहा है।",
                "क्या? आपने क्या कहा? क्या?",
                "मुझे बार-बार फोन करना बंद करो! मैं अभी फोन रख रही हूँ!",
                "",  # Silent patient
                "आज मौसम बहुत अच्छा है, डाकिया कुछ सुंदर फूल लाया है।" # Wandering patient
            ]
        elif preferred_language == "Hinglish":
            replies = [
                f"Haan beta, maine apni {medication} paani ke saath le li hai.",
                f"Maine subah nashte ke saath ise pehle hi le liya tha, dear.",
                "Kya aap mujhe 15 minutes mein phir se call kar sakte hain? Main abhi apna favourite show dekh rahi hoon.",
                f"Nahi, mujhe aaj ye {medication} ki goli nahi khani.",
                "Kaun bol raha hai? Aap kis goli ki baat kar rahe hain?",
                "Mujhe bahut chakkar aa rahe hain aur mera sir dard kar raha hai.",
                "Kya? Aapne kya kaha? Kya?",
                "Mujhe baar-baar call karna band karo! Main abhi phone rakh rahi hoon!",
                "",  # Silent patient
                "Aaj mausam bahut accha hai, postman bahut sundar phool laya hai." # Wandering patient
            ]
        else:
            replies = [
                f"Yes, I just took my {medication} with water.",
                f"I already had it with my breakfast earlier, dear.",
                "Can you call me back in 15 minutes? I am watching my favorite show right now.",
                f"No, I don't want to take this {medication} pill today.",
                "Who is this? What pills are you talking about?",
                "I'm feeling very dizzy and my head hurts.",
                "What? What did you say? What?",
                "Stop calling me! I am hanging up now!",
                "",  # Silent patient
                "The weather is very nice today, the mailman brought some nice flowers." # Wandering patient
            ]
        return random.choice(replies)

    system_prompt = f"""You are simulating an elderly patient named {patient_name} who is being called by an AI caregiver reminder to take their {medication} ({dosage}).

Based on the caregiver's statement, reply as {patient_name}. Speak slowly, in short sentences.
"""

    if preferred_language == "Hindi":
        system_prompt += "\nYou MUST reply entirely in Devanagari Hindi (using Devanagari script). Your reply should sound like an elderly Indian person speaking Hindi.\n"
    elif preferred_language == "Hinglish":
        system_prompt += "\nYou MUST reply entirely in Hinglish (Hindi written in Latin script, e.g. 'Haan beta, maine le liya'). Your reply should sound like an elderly Indian person speaking Hinglish.\n"

    system_prompt += """
Choose ONE of these random personas for this call:
1. Cooperative: Takes the pill immediately (e.g. "Yes, I am taking it now dear" or Hinglish "Haan beta, abhi le leti hoon").
2. Took it already: Took it earlier with breakfast or lunch.
3. Forgetful/Snooze: Asks to call back in 10 or 15 minutes.
4. Uncooperative/Refused: Dislikes the pill or refuses it.
5. Confused: Asks who is calling and what pills.
6. Unwell: Mentions feeling dizzy, tired, or having a headache.
7. Forgetful (Confusion/Hearing): Answers "What? What did you say?" or similar hearing confusion to every question.
8. Angry: Irritated by the call, tells the caller to stop calling and tries to hang up.
9. Silent: Patient says absolutely nothing, returns an empty string "".
10. Wandering: Tells completely off-topic stories (e.g. about pets, weather, childhood) and ignores the pill reminder.

Your output MUST be ONLY the spoken text of the patient. Keep it short, natural, and realistic for an elderly person. If you chose the 'Silent' persona, output nothing at all (empty response). Do NOT add any notes, headers, or markdown blocks."""

    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"MedRemind Assistant: \"{last_agent_speech}\""}
    ]
    
    try:
        reply = call_llm(prompt, response_json=False)
        reply = re.sub(r'^["\']|["\']$', '', reply.strip())
        if not reply:
            return ""
        return reply
    except Exception:
        if preferred_language == "Hindi":
            return "हाँ जी, मैंने अभी ले ली।"
        elif preferred_language == "Hinglish":
            return "Haan ji, maine abhi le li."
        else:
            return "Yes, I just took it dear."

