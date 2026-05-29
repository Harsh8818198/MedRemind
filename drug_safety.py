import requests
import urllib.parse
import re

# Offline Database: A curated clinical database of common critical drug-drug interactions
# Used for instant offline demo capabilities and high-priority matching
OFFLINE_DDI_DATABASE = [
    {
        "pair": ["aspirin", "warfarin"],
        "severity": "CRITICAL",
        "warning": "Concurrent use of Aspirin and Warfarin significantly increases the risk of severe gastrointestinal and internal bleeding."
    },
    {
        "pair": ["ibuprofen", "warfarin"],
        "severity": "CRITICAL",
        "warning": "NSAIDs like Ibuprofen increase the risk of bleeding and ulceration when taken with anticoagulants like Warfarin."
    },
    {
        "pair": ["lisinopril", "spironolactone"],
        "severity": "HIGH",
        "warning": "Taking Lisinopril with Spironolactone or Potassium supplements can lead to Hyperkalemia (dangerous high potassium levels) which impacts heart rhythms."
    },
    {
        "pair": ["nitroglycerin", "sildenafil"],
        "severity": "CRITICAL",
        "warning": "Co-administration of Nitroglycerin and Sildenafil (Viagra) can cause a sudden, life-threatening drop in blood pressure (severe hypotension)."
    },
    {
        "pair": ["viagra", "nitroglycerin"],
        "severity": "CRITICAL",
        "warning": "Co-administration of Viagra (Sildenafil) and Nitroglycerin can cause a sudden, life-threatening drop in blood pressure (severe hypotension)."
    },
    {
        "pair": ["simvastatin", "grapefruit juice"],
        "severity": "MEDIUM",
        "warning": "Grapefruit increases Simvastatin blood concentrations, raising the risk of muscle toxicity and kidney strain (rhabdomyolysis)."
    },
    {
        "pair": ["amiodarone", "warfarin"],
        "severity": "HIGH",
        "warning": "Amiodarone inhibits Warfarin metabolism, significantly increasing its blood concentration and bleeding risk."
    },
    {
        "pair": ["ciprofloxacin", "calcium"],
        "severity": "MEDIUM",
        "warning": "Calcium supplements bind to Ciprofloxacin, severely reducing antibiotic absorption and rendering it ineffective."
    },
    {
        "pair": ["ibuprofen", "aspirin"],
        "severity": "MEDIUM",
        "warning": "Ibuprofen can block the antiplatelet cardioprotective effect of low-dose daily Aspirin."
    },
    {
        "pair": ["metformin", "contrast dye"],
        "severity": "HIGH",
        "warning": "Iodinated contrast dye used in imaging can impair kidney function, leading to Metformin accumulation and lactic acidosis."
    }
]

# Simple in-memory cache to prevent multiple slow network calls to OpenFDA
_fda_cache = {}

def get_fda_label(medication_name: str) -> dict:
    """Fetch drug label information from api.fda.gov with local memory caching."""
    med_clean = medication_name.strip().lower()
    if med_clean in _fda_cache:
        return _fda_cache[med_clean]
        
    encoded_med = urllib.parse.quote(f'"{med_clean}"')
    # Query brand_name OR generic_name
    url = (
        f"https://api.fda.gov/drug/label.json?"
        f"search=(openfda.brand_name:{encoded_med}+OR+openfda.generic_name:{encoded_med})"
        f"&limit=1"
    )
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "results" in data and len(data["results"]) > 0:
                result = data["results"][0]
                _fda_cache[med_clean] = result
                return result
        # Save empty dict in cache on failure so we don't repeat failed calls
        _fda_cache[med_clean] = {}
        return {}
    except Exception as e:
        print(f"[OpenFDA Link Warning] Failed to reach api.fda.gov for '{medication_name}': {e}")
        return {}

def check_interactions(medication_list: list[str]) -> list[dict]:
    """
    Cross-references a list of medications to detect critical drug conflicts.
    Combines local offline heuristics with dynamic OpenFDA REST queries.
    """
    conflicts = []
    # Normalize list
    meds = [m.strip().lower() for m in medication_list if m.strip()]
    
    # Check all unique pairs (A, B)
    for i in range(len(meds)):
        for j in range(i + 1, len(meds)):
            med_a = meds[i]
            med_b = meds[j]
            
            # --- 1. CHECK OFFLINE DATABASE FIRST (Instant & Reliable) ---
            offline_match = None
            for interaction in OFFLINE_DDI_DATABASE:
                pair = interaction["pair"]
                if (med_a == pair[0] and med_b == pair[1]) or (med_b == pair[0] and med_a == pair[1]):
                    offline_match = interaction
                    break
                    
            if offline_match:
                conflicts.append({
                    "drug_a": medication_list[i],
                    "drug_b": medication_list[j],
                    "warning": offline_match["warning"],
                    "severity": offline_match["severity"]
                })
                continue
                
            # --- 2. DYNAMIC ONLINE OPENFDA MATCHING ---
            label_a = get_fda_label(med_a)
            # Check if Drug A mentions Drug B in interactions
            interactions_a = " ".join(label_a.get("drug_interactions", []))
            
            if med_b in interactions_a.lower():
                # Extract relevant warning snippet
                snippet = f"FDA label warning: Concurrent use of {medication_list[i]} and {medication_list[j]} was flagged in interactions data."
                # Regex try to extract sentence containing drug B
                sentences = re.split(r'\.|\n', interactions_a)
                for sentence in sentences:
                    if med_b in sentence.lower() and len(sentence.strip()) > 10:
                        snippet = sentence.strip() + "."
                        break
                        
                conflicts.append({
                    "drug_a": medication_list[i],
                    "drug_b": medication_list[j],
                    "warning": snippet,
                    "severity": "HIGH"
                })
                continue
                
            # Check reverse: Drug B label mentions Drug A
            label_b = get_fda_label(med_b)
            interactions_b = " ".join(label_b.get("drug_interactions", []))
            
            if med_a in interactions_b.lower():
                snippet = f"FDA label warning: Concurrent use of {medication_list[j]} and {medication_list[i]} was flagged in interactions data."
                sentences = re.split(r'\.|\n', interactions_b)
                for sentence in sentences:
                    if med_a in sentence.lower() and len(sentence.strip()) > 10:
                        snippet = sentence.strip() + "."
                        break
                        
                conflicts.append({
                    "drug_a": medication_list[i],
                    "drug_b": medication_list[j],
                    "warning": snippet,
                    "severity": "HIGH"
                })
                
    return conflicts

def validate_new_medication(new_med: str, existing_meds: list[str]) -> dict:
    """
    Validates if adding a new medication to the patient's schedule is safe.
    Called before saving new reminders.
    """
    if not existing_meds:
        return {"safe": True, "warnings": []}
        
    full_list = existing_meds + [new_med]
    conflicts = check_interactions(full_list)
    
    # Filter conflicts that actually involve the new medication
    med_clean = new_med.strip().lower()
    new_warnings = []
    
    for c in conflicts:
        if c["drug_a"].strip().lower() == med_clean or c["drug_b"].strip().lower() == med_clean:
            new_warnings.append(c)
            
    is_safe = len(new_warnings) == 0
    return {
        "safe": is_safe,
        "warnings": new_warnings
    }
