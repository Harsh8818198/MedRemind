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

At each step of the conversation, analyze the patient's statement and classify the status into ONE of the following 8 outcomes:
1. `TAKEN` — The patient confirms they have just taken the medication in your presence.
2. `TAKEN_EARLIER` — The patient reports they already took it prior to this call (e.g. "I had it with breakfast").
3. `SNOOZE` — The patient asks to be called back later or in a specific amount of time (e.g. "Call me in 15 minutes").
4. `REFUSED` — The patient actively refuses to take the medication (e.g. "I don't want it", "I'm not taking that").
5. `CONFUSED` — The patient exhibits confusion, doesn't know who you are, or is confused about their pills (e.g. "Who is this?", "What pills?").
6. `MEDICAL_CONCERN` — The patient mentions feeling sick, dizzy, in pain, or has a physical complaint (e.g. "I feel very dizzy", "My stomach hurts").
7. `NO_RESPONSE` — The patient says nothing or line was silent.
8. `OTHER` — The response does not fit any of the above categories, or requires further discussion.

You MUST respond strictly in the following JSON format. Do NOT include any markdown blocks, wrapping, or extra text. Output ONLY valid JSON:
{
  "spoken_reply": "Your warm, slow, and clear spoken reply to the patient",
  "outcome": "TAKEN | TAKEN_EARLIER | SNOOZE | REFUSED | CONFUSED | MEDICAL_CONCERN | NO_RESPONSE | OTHER",
  "end_call": true_or_false_boolean,
  "guardian_note": "A concise status update for the guardian explaining what is happening."
}

Rules for ending calls:
- If outcome is TAKEN, TAKEN_EARLIER, REFUSED, or SNOOZE, set `end_call` to true.
- If outcome is CONFUSED or MEDICAL_CONCERN, set `end_call` to true (we will escalate to guardian immediately).
- For OTHER, set `end_call` to false so you can continue the conversation to clarify, unless you've had 4+ turns.
"""

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

    # Identify outcome based on keyword matching
    outcome = "OTHER"
    spoken_reply = "I understand, dear. Could you tell me if you've taken your pills yet?"
    end_call = False
    guardian_note = "Conversing with patient."

    if not latest_msg or latest_msg.strip() == "":
        outcome = "NO_RESPONSE"
        spoken_reply = "Hello? Are you there, dear? It's time for your medication."
        guardian_note = "No sound or response from patient."
    elif any(word in latest_msg for word in ["yes", "took", "had it", "taken", "done", "already"]):
        if any(word in latest_msg for word in ["earlier", "morning", "breakfast", "already"]):
            outcome = "TAKEN_EARLIER"
            spoken_reply = "Oh, excellent! I'm glad you already took it. Have a wonderful day!"
            end_call = True
            guardian_note = "Patient took the medication earlier."
        else:
            outcome = "TAKEN"
            spoken_reply = "Wonderful! Thank you for taking it. Keep resting, and I will call you for the next one."
            end_call = True
            guardian_note = "Patient confirmed taking the medication just now."
    elif any(word in latest_msg for word in ["later", "minutes", "snooze", "hour", "call me back"]):
        outcome = "SNOOZE"
        spoken_reply = "No problem at all! I will call you back in a little bit so you can take it then."
        end_call = True
        guardian_note = "Patient requested a snooze / call back."
    elif any(word in latest_msg for word in ["don't want", "no", "refuse", "won't", "stop", "hate"]):
        outcome = "REFUSED"
        spoken_reply = "I understand you feel that way, dear, but these are important. I will let your guardian know so they can check in on you."
        end_call = True
        guardian_note = "Patient refused to take their medication."
    elif any(word in latest_msg for word in ["who", "what", "where", "scared", "confuse"]):
        outcome = "CONFUSED"
        spoken_reply = "Don't worry, dear, it's just MedRemind calling to help you with your pills. I'll let your family know to call you shortly."
        end_call = True
        guardian_note = "Patient sounded confused or did not recognize the system."
    elif any(word in latest_msg for word in ["dizzy", "hurt", "pain", "sick", "vomit", "dreadful", "bad"]):
        outcome = "MEDICAL_CONCERN"
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
    def __init__(self, patient_name: str, medication: str, dosage: str):
        self.patient_name = patient_name
        self.medication = medication
        self.dosage = dosage
        
        custom_system = SYSTEM_PROMPT + f"\nToday, you are reminding {patient_name} to take their medication: {medication} (Dosage: {dosage})."
        
        self.history = [
            {"role": "system", "content": custom_system}
        ]
        self.transcript = []
        self.turn_count = 0

    def start_call(self) -> str:
        greeting = f"Hello {self.patient_name}, this is your helper calling. It is time to take your {self.medication}, dosage {self.dosage}. Have you taken it yet?"
        self.history.append({"role": "assistant", "content": greeting})
        self.transcript.append({"role": "Agent", "text": greeting})
        return greeting

    def process_turn(self, patient_input: str) -> dict:
        self.turn_count += 1
        self.history.append({"role": "user", "content": patient_input})
        self.transcript.append({"role": "Patient", "text": patient_input})
        
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
            # Try to find JSON boundary {...}
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
            
            # Clean reasoning/thoughts prefixes (Gemma details)
            clean_text = re.sub(r"^\*.*?\n", "", clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r"^Constraint.*?\n", "", clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r"^[a-zA-Z\s]+:\s*.*?$", "", clean_text, flags=re.MULTILINE) # remove labels like 'spoken_reply:'
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


def generate_patient_reply(patient_name: str, medication: str, dosage: str, last_agent_speech: str) -> str:
    """Simulates a patient's response using LLM (or mock fallbacks) for automated background runs."""
    if not HAS_KEYS:
        # Graceful random offline mock fallback
        replies = [
            f"Yes, I just took my {medication} with water.",
            f"I already had it with my breakfast earlier, dear.",
            "Can you call me back in 15 minutes? I am watching my favorite show right now.",
            f"No, I don't want to take this {medication} pill today.",
            "Who is this? What pills are you talking about?",
            "I'm feeling very dizzy and my head hurts."
        ]
        return random.choice(replies)

    system_prompt = f"""You are simulating an elderly patient named {patient_name} who is being called by an AI caregiver reminder to take their {medication} ({dosage}).

Based on the caregiver's statement, reply as {patient_name}. Speak slowly, in short sentences. Sometimes you are cooperative, sometimes you are a bit forgetful or slow, and occasionally you might complain of feeling slightly dizzy, ask to snooze, or be a bit confused. 

Choose ONE of these random personas for this call:
1. Cooperative (takes the pill immediately).
2. Took it already (took it earlier with breakfast/lunch).
3. Forgetful/Snooze (asks to call back in 10 or 15 minutes).
4. Uncooperative/Refused (dislikes the pill or refuses it).
5. Confused (asks who is calling and what pills).
6. Unwell (mentions feeling dizzy, tired, or having a headache).

Your output MUST be ONLY the spoken text of the patient. Keep it short, natural, and realistic for an elderly person. Do NOT add any notes, headers, or markdown blocks."""

    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"MedRemind Assistant: \"{last_agent_speech}\""}
    ]
    
    try:
        reply = call_llm(prompt, response_json=False)
        # Re-verify and clean any markdown blocks or quotes
        reply = re.sub(r'^["\']|["\']$', '', reply.strip())
        return reply if reply else "Yes, I am here dear."
    except Exception:
        return "Yes, I just took it dear."

