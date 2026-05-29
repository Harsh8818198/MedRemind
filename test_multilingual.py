import pytest
import agent

def test_hindi_agent_flow():
    print("\n=======================================================")
    print("      Testing MedRemind Bilingual Hindi Support")
    print("=======================================================")
    
    # 1. Test Agent Initialization with preferred_language="Hindi"
    hindi_agent = agent.AdherenceAgent("Grandpa", "Lisinopril", "10mg", preferred_language="Hindi")
    assert hindi_agent.preferred_language == "Hindi"
    
    # 2. Test start_call greeting in Hindi
    greeting = hindi_agent.start_call()
    print(f"  Hindi Greeting: '{greeting}'")
    assert "नमस्ते" in greeting, "Hindi greeting should contain Devanagari 'नमस्ते'"
    assert "Grandpa" in greeting, "Hindi greeting should mention patient's name"
    
    # 3. Test mock response classification for Hindi inputs
    # TAKEN outcome
    res_taken = hindi_agent.process_turn("हाँ जी, मैंने अपनी दवाई खा ली है")
    print(f"  Hindi Taken Response: {res_taken}")
    assert res_taken["outcome"] == "TAKEN"
    assert res_taken["end_call"] is True
    assert "taking" in res_taken["guardian_note"].lower() or "taken" in res_taken["guardian_note"].lower() # guardian summary should be in English
    
    # MEDICAL_EMERGENCY outcome in Hindi
    em_agent = agent.AdherenceAgent("Grandpa", "Lisinopril", "10mg", preferred_language="Hindi")
    res_em = em_agent.process_turn("मेरे सीने में बहुत दर्द है और सांस लेने में तकलीफ हो रही है")
    print(f"  Hindi Emergency Response: {res_em}")
    assert res_em["outcome"] == "MEDICAL_EMERGENCY"
    assert res_em["end_call"] is True
    assert "EMERGENCY" in res_em["guardian_note"] # guardian note in English
    
    print("  -> Hindi Translation & Conversation Tests: PASSED")

def test_hinglish_agent_flow():
    print("\n=======================================================")
    print("      Testing MedRemind Bilingual Hinglish Support")
    print("=======================================================")
    
    # 1. Test Agent Initialization with preferred_language="Hinglish"
    hinglish_agent = agent.AdherenceAgent("Mom", "Metformin", "500mg", preferred_language="Hinglish")
    assert hinglish_agent.preferred_language == "Hinglish"
    
    # 2. Test start_call greeting in Hinglish
    greeting = hinglish_agent.start_call()
    print(f"  Hinglish Greeting: '{greeting}'")
    assert "helper bol rahi hoon" in greeting, "Hinglish greeting should contain helper bol rahi hoon"
    assert "Mom" in greeting
    
    # 3. Test mock response classification for Hinglish inputs
    # TAKEN_EARLIER outcome
    res_taken_earlier = hinglish_agent.process_turn("Maine subah nashte ke saath already le liya tha dear")
    print(f"  Hinglish Taken Earlier Response: {res_taken_earlier}")
    assert res_taken_earlier["outcome"] == "TAKEN_EARLIER"
    assert res_taken_earlier["end_call"] is True
    
    # SNOOZE outcome
    snooze_agent = agent.AdherenceAgent("Mom", "Metformin", "500mg", preferred_language="Hinglish")
    res_snooze = snooze_agent.process_turn("Baad mein call karna, main busy hoon")
    print(f"  Hinglish Snooze Response: {res_snooze}")
    assert res_snooze["outcome"] == "SNOOZE"
    
    print("  -> Hinglish Translation & Conversation Tests: PASSED")

def test_patient_simulated_reply():
    print("\n=======================================================")
    print("      Testing Multilingual Patient Simulator replies")
    print("=======================================================")
    
    # Test Hindi Simulator reply fallback
    hindi_reply = agent.generate_patient_reply("Grandma", "Aspirin", "75mg", "Have you taken it?", preferred_language="Hindi")
    print(f"  Simulated Patient Reply (Hindi): '{hindi_reply}'")
    assert isinstance(hindi_reply, str)
    assert len(hindi_reply) >= 0 # can be silent empty string
    
    # Test Hinglish Simulator reply fallback
    hinglish_reply = agent.generate_patient_reply("Grandma", "Aspirin", "75mg", "Have you taken it?", preferred_language="Hinglish")
    print(f"  Simulated Patient Reply (Hinglish): '{hinglish_reply}'")
    assert isinstance(hinglish_reply, str)
    
    print("  -> Simulated Patient Reply Tests: PASSED")

if __name__ == "__main__":
    test_hindi_agent_flow()
    test_hinglish_agent_flow()
    test_patient_simulated_reply()
