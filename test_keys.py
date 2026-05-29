import os
import sys
import requests

def test_gemini_key(api_key: str) -> tuple[bool, str]:
    """
    Test a single Gemini API key against the models list endpoint.
    Returns (is_valid, error_or_success_message).
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get("models", [])
            # Find a few common models to confirm key capabilities
            model_names = [m["name"].split("/")[-1] for m in models[:3]]
            return True, f"Valid key. Available sample models: {', '.join(model_names)}"
        else:
            try:
                err_msg = response.json()["error"]["message"]
            except Exception:
                err_msg = response.text
            return False, f"Invalid (HTTP {response.status_code}): {err_msg}"
    except Exception as e:
        return False, f"Connection failed: {e}"

def update_env_file(working_key: str):
    """Write the working Gemini key into the .env file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        # Create default .env if missing
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEY=\nMODEL_NAME=gemma-4-31b-it\nVOICE_MODE=text\nPATIENT_NAME=Grandpa\n")
            
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={working_key}\n")
                updated = True
            else:
                new_lines.append(line)
                
        if not updated:
            new_lines.append(f"\nGEMINI_API_KEY={working_key}\n")
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        return True
    except Exception as e:
        print(f"Failed to auto-configure .env file: {e}")
        return False

def main():
    print("\n===========================================================================")
    print("           ♊  Gemini API Key Stack Validator  ♊")
    print("===========================================================================")
    
    # Check if keys are provided as arguments or keys.txt file, or interactive paste
    keys = []
    
    keys_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.txt")
    if os.path.exists(keys_file):
        print(f"Reading keys from local file: {keys_file}")
        with open(keys_file, "r", encoding="utf-8") as f:
            for line in f:
                k = line.strip()
                # Skip comments or empty lines
                if k and not k.startswith("#"):
                    keys.append(k)
    
    if not keys:
        print("Please paste your Gemini API keys here (one per line).")
        print("When you are done, press Enter on an empty line or Ctrl+D/Ctrl+Z:")
        try:
            while True:
                line = input().strip()
                if not line:
                    break
                keys.append(line)
        except (KeyboardInterrupt, EOFError):
            pass

    if not keys:
        print("\n[Error] No API keys entered. Exiting.")
        sys.exit(1)
        
    print(f"\nTesting {len(keys)} keys from your stack...\n")
    
    working_keys = []
    
    for idx, key in enumerate(keys):
        # Truncate key for display safety
        display_key = key[:6] + "..." + key[-6:] if len(key) > 12 else "Invalid Format Key"
        print(f"[{idx + 1}/{len(keys)}] Testing key {display_key}...", end="", flush=True)
        
        is_valid, msg = test_gemini_key(key)
        
        if is_valid:
            print(f"\r[{idx + 1}/{len(keys)}] Key {display_key} -> \033[92m[WORKING]\033[0m")
            print(f"      Status: {msg}\n")
            working_keys.append(key)
        else:
            print(f"\r[{idx + 1}/{len(keys)}] Key {display_key} -> \033[91m[FAILED]\033[0m")
            print(f"      Error: {msg}\n")
            
    print("===========================================================================")
    print(f"Scan complete! {len(working_keys)} of {len(keys)} keys are working.")
    print("===========================================================================")
    
    if working_keys:
        print(f"\nWorking key found: {working_keys[0][:6]}...{working_keys[0][-6:]}")
        auto_write = input("Would you like to automatically configure the first working key to your .env? (y/n): ").strip().lower()
        if auto_write in ["y", "yes", ""]:
            if update_env_file(working_keys[0]):
                print("\033[92m[Success]\033[0m .env file updated successfully with your active Gemini API key!")
                print("You can now run 'python main.py test' using your live Gemini account!")
            else:
                print("[Error] Failed to write to .env.")
    else:
        print("\n\033[91m[Warning]\033[0m No working keys were found. Please verify your keys or project access in Google AI Studio.")

if __name__ == "__main__":
    main()
