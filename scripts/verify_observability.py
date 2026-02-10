import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"
ADMIN_TOKEN = sys.argv[1] if len(sys.argv) > 1 else None

if not ADMIN_TOKEN:
    print("❌ Usage: python verify_observability.py <TOK>")
    print("   Please provide an admin token.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {ADMIN_TOKEN}",
    "Content-Type": "application/json"
}

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def test_config_endpoints():
    print_section("1. Testing Config Endpoints")
    
    # GET Config
    print("🔹 Getting current config...")
    res = requests.get(f"{BASE_URL}/observability/config", headers=HEADERS)
    if res.status_code != 200:
        print(f"❌ Failed to get config: {res.text}")
        return False
        
    config = res.json()
    print(f"✅ Current Config: {json.dumps(config, indent=2)}")
    
    # UPDATE Config (test log level change)
    print("\n🔹 Updating Log Level to DEBUG...")
    update_res = requests.put(
        f"{BASE_URL}/observability/config", 
        headers=HEADERS,
        json={"log_level": "DEBUG"}
    )
    
    if update_res.status_code == 200:
        print("✅ Log level updated successfully")
    else:
        print(f"❌ Failed to update config: {update_res.text}")
        return False
        
    # Revert to INFO
    requests.put(f"{BASE_URL}/observability/config", headers=HEADERS, json={"log_level": "INFO"})
    print("✅ Reverted Log Level to INFO")
    return True

def test_usage_endpoints():
    print_section("2. Testing Usage Statistics")
    
    # GET Usage
    res = requests.get(f"{BASE_URL}/observability/usage?period=24h", headers=HEADERS)
    if res.status_code == 200:
        stats = res.json()
        print(f"✅ Usage Stats (24h): {json.dumps(stats, indent=2)}")
        
        # Check structure
        if "llm" in stats and "embedding" in stats:
            print("✅ Stats structure is correct")
        else:
            print("❌ Stats structure mismatch")
    else:
        print(f"❌ Failed to get usage stats: {res.text}")

def test_log_emission():
    print_section("3. Testing Log Emission")
    res = requests.post(
        f"{BASE_URL}/observability/test-log?level=WARNING&message=VerificationScriptTest",
        headers=HEADERS
    )
    if res.status_code == 200:
        print("✅ Test log emitted successfully")
    else:
        print(f"❌ Failed to emit test log: {res.text}")

if __name__ == "__main__":
    try:
        if test_config_endpoints():
            test_usage_endpoints()
            test_log_emission()
            print("\n✅ VERIFICATION COMPLETE")
    except Exception as e:
        print(f"\n❌ Verification failed with exception: {e}")
