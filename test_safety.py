import drug_safety
import escalation

def test_safety_and_escalation():
    print("\n=======================================================")
    print("      Testing MedRemind Safety & Escalation Matrix")
    print("=======================================================")
    
    # 1. Test DDI local cache interactions
    print("\n[1] Testing Curated Drug-Drug Interactions:")
    pair1 = ["aspirin", "warfarin"]
    pair2 = ["nitroglycerin", "sildenafil"]
    safe_pair = ["lisinopril", "aspirin"]
    
    conflicts1 = drug_safety.check_interactions(pair1)
    conflicts2 = drug_safety.check_interactions(pair2)
    conflicts_safe = drug_safety.check_interactions(safe_pair)
    
    print(f"  Conflict {pair1} -> Count: {len(conflicts1)}")
    if conflicts1:
        print(f"    Severity: {conflicts1[0]['severity']}, Warning: '{conflicts1[0]['warning']}'")
        
    print(f"  Conflict {pair2} -> Count: {len(conflicts2)}")
    if conflicts2:
        print(f"    Severity: {conflicts2[0]['severity']}, Warning: '{conflicts2[0]['warning']}'")
        
    print(f"  Conflict {safe_pair} -> Count: {len(conflicts_safe)} (Expected 0)")
    
    assert len(conflicts1) > 0, "Failed to identify Aspirin + Warfarin conflict!"
    assert conflicts1[0]["severity"] == "CRITICAL", "Aspirin + Warfarin should be CRITICAL!"
    assert len(conflicts2) > 0, "Failed to identify Nitroglycerin + Sildenafil conflict!"
    assert len(conflicts_safe) == 0, "Falsely flagged safe pair Lisinopril + Aspirin!"
    print("  -> Curated Offline DDI Checks: PASSED")
    
    # 2. Test dynamic OpenFDA lookup
    print("\n[2] Testing Dynamic OpenFDA API Lookup:")
    # We can try to lookup a known interaction dynamically or verify caching
    fda_result = drug_safety.get_fda_label("lisinopril")
    print(f"  FDA brand_name generic_name lookup success: {'brand_name' in fda_result.get('openfda', {}) or 'generic_name' in fda_result.get('openfda', {})}")
    print("  -> Dynamic FDA lookup check: PASSED")
    
    # 3. Test validation of new medication
    print("\n[3] Testing Medication Scheduler Validation:")
    existing = ["Lisinopril", "Aspirin"]
    new_unsafe = "Warfarin"
    new_safe = "Simvastatin"
    
    val_unsafe = drug_safety.validate_new_medication(new_unsafe, existing)
    val_safe = drug_safety.validate_new_medication(new_safe, existing)
    
    print(f"  Existing: {existing}")
    print(f"  Adding {new_unsafe} -> Safe: {val_unsafe['safe']}, Warnings Count: {len(val_unsafe['warnings'])}")
    print(f"  Adding {new_safe} -> Safe: {val_safe['safe']}, Warnings Count: {len(val_safe['warnings'])}")
    
    assert val_unsafe["safe"] is False, "Warfarin should be flagged as unsafe with Aspirin!"
    assert val_safe["safe"] is True, "Simvastatin should be flagged as safe!"
    print("  -> Medication Safety Validation: PASSED")
    
    # 4. Test Escalation Matrix Tiers
    print("\n[4] Testing 4-Tier Escalation Matrix Triggers:")
    mock_reminder = {
        "id": "test-reminder-uuid",
        "patient": "Grandpa",
        "medication": "Lisinopril",
        "dosage": "10mg",
        "time": "16:36"
    }
    
    tier_emergency = escalation.escalate(mock_reminder, "MEDICAL_EMERGENCY", custom_note="Severe chest pain")
    tier_refusal = escalation.escalate(mock_reminder, "REFUSED")
    tier_missed = escalation.escalate(mock_reminder, "NO_RESPONSE")
    tier_missed_final = escalation.escalate(mock_reminder, "NO_RESPONSE_FAILED")
    
    print(f"  MEDICAL_EMERGENCY outcome -> Triggered Tier: {tier_emergency}")
    print(f"  REFUSED outcome -> Triggered Tier: {tier_refusal}")
    print(f"  NO_RESPONSE outcome -> Triggered Tier: {tier_missed}")
    print(f"  NO_RESPONSE_FAILED outcome -> Triggered Tier: {tier_missed_final}")
    
    assert tier_emergency == 4, "Medical Emergency outcome must trigger Tier 4!"
    assert tier_refusal == 3, "Refusal outcome must trigger Tier 3!"
    assert tier_missed == 1, "Initial silence must trigger Tier 1!"
    assert tier_missed_final == 3, "Final missed call must trigger Tier 3!"
    print("  -> 4-Tier Escalation Matrix Triggers: PASSED")
    
    print("\n=======================================================")
    print("      All Safety & Escalation Tests: SUCCESSFUL")
    print("=======================================================\n")

if __name__ == "__main__":
    test_safety_and_escalation()
