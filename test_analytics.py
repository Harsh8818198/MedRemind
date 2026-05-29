import analytics
import storage
import agent

def test_clinical_engine():
    print("\n=======================================================")
    print("      Testing MedRemind Clinical Intelligence Engine")
    print("=======================================================")
    
    # 1. Test coherence score calculation
    test_agent = agent.AdherenceAgent("Grandpa", "Lisinopril", "10mg")
    
    print("\n[1] Testing Semantic Coherence Scores:")
    coherent_text = "Yes dear I just took my Lisinopril medication"
    incoherent_text = "the mailman brought red roses because the flight was delayed"
    empty_text = ""
    
    coherent_score = test_agent.calculate_coherence_score(coherent_text)
    incoherent_score = test_agent.calculate_coherence_score(incoherent_text)
    empty_score = test_agent.calculate_coherence_score(empty_text)
    
    print(f"  Coherent text: '{coherent_text}' -> Score: {coherent_score} (Expected high)")
    print(f"  Incoherent text: '{incoherent_text}' -> Score: {incoherent_score} (Expected low)")
    print(f"  Empty text: '' -> Score: {empty_score} (Expected 0.0)")
    
    assert coherent_score > incoherent_score, "Coherence calculation failed comparison test."
    assert empty_score == 0.0, "Empty coherence should be exactly 0.0"
    print("  -> Semantic Coherence Tests: PASSED")
    
    # 2. Test response latency calculation
    print("\n[2] Testing Response Latencies:")
    turn_res = test_agent.process_turn("Yes dear, taken.")
    latency = turn_res.get("response_latency_sec")
    coherence = turn_res.get("coherence_score")
    outcome = turn_res.get("outcome")
    
    print(f"  Turn result outcome: {outcome}")
    print(f"  Turn latency: {latency}s")
    print(f"  Turn coherence score: {coherence}")
    
    assert latency is not None and latency > 0, "Latency was not recorded."
    assert coherence is not None and coherence > 0, "Coherence was not attached."
    print("  -> Response Latency and Coherence Attachment: PASSED")
    
    # 3. Test medical emergency trigger
    print("\n[3] Testing Critical Emergency keyword overrides:")
    emergency_text = "I'm having severe chest pain and can't breathe"
    em_agent = agent.AdherenceAgent("Grandpa", "Lisinopril", "10mg")
    em_res = em_agent.process_turn(emergency_text)
    
    print(f"  Emergency input: '{emergency_text}'")
    print(f"  Outcome: {em_res.get('outcome')}")
    print(f"  End call: {em_res.get('end_call')}")
    print(f"  Spoken response: '{em_res.get('spoken_reply')}'")
    
    assert em_res.get("outcome") == "MEDICAL_EMERGENCY", "Emergency outcome override failed!"
    assert em_res.get("end_call") is True, "Emergency call should end immediately!"
    print("  -> Medical Emergency Keyword Trigger: PASSED")
    
    # 4. Test Predictor and Cognitive Tracker
    print("\n[4] Testing Predictor & Cognitive Trends:")
    predictor = analytics.AdherencePredictor()
    predictor.train() # May not train due to log size, fallback to heuristics will trigger
    
    test_reminder = {
        "id": "test-id-123",
        "patient": "Grandpa",
        "medication": "Lisinopril",
        "dosage": "10mg",
        "next_run": "16:36"
    }
    
    risk = predictor.predict_risk(test_reminder)
    print(f"  ML/Heuristic predicted risk for reminder: {risk:.2f}")
    assert 0.0 <= risk <= 1.0, "Adherence risk must be in range [0, 1]."
    
    trend = analytics.CognitiveTracker.get_trend("Grandpa", days=30)
    print(f"  Historical trend values count: {len(trend.get('timestamps', []))}")
    print(f"  Coherence trend list: {trend.get('coherence_scores')}")
    print(f"  Latency trend list: {trend.get('response_latencies')}")
    
    decline = analytics.CognitiveTracker.detect_decline("Grandpa")
    print(f"  Cognitive decline status detected: {decline}")
    
    print("  -> Predictor & Trend Analyzer Tests: PASSED")
    
    print("\n=======================================================")
    print("        All Clinical Engine Tests: SUCCESSFUL")
    print("=======================================================\n")

if __name__ == "__main__":
    test_clinical_engine()
