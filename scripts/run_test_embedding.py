import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"
USERNAME = "admin"
PASSWORD = "admin123"  # Default from config.py

def login():
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD})
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        print(f"Login failed: {e}")
        try:
            # Try fallback password
            response = requests.post(f"{BASE_URL}/auth/login", json={"username": USERNAME, "password": "admin"})
            response.raise_for_status()
            return response.json()["access_token"]
        except Exception as e2:
            print(f"Login failed (fallback): {e2}")
            sys.exit(1)

def get_first_connection(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/data/connections", headers=headers)
    response.raise_for_status()
    connections = response.json()
    if not connections:
        print("No database connections found. Creating a test one...")
        # Create a test connection (assuming local postgres for now, or fail)
        return create_test_connection(token)
    return connections[0]

def create_test_connection(token):
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "name": "Test Connection",
        "uri": "postgresql://admin:admin@localhost:5432/Spice_BD", # Default fallback
        "engine_type": "postgresql"
    }
    response = requests.post(f"{BASE_URL}/data/connections", json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def publish_test_config(token, connection_id):
    headers = {"Authorization": f"Bearer {token}"}
    
    # minimal schema
    schema_selection = {"users": ["id", "username"]} 
    
    data = {
        "prompt_text": "You are a test assistant.",
        "user_id": "admin",
        "connection_id": connection_id,
        "schema_selection": json.dumps(schema_selection),
        "data_dictionary": "# Test Dictionary\nTest data.",
        "reasoning": json.dumps({"note": "This is a test config"}),
        "example_questions": json.dumps(["Test question?"]),
        "embedding_config": json.dumps({"model": "BAAI/bge-m3", "chunkSize": 500, "chunkOverlap": 50}),
        "retriever_config": json.dumps({"topKInitial": 10, "topKFinal": 5})
    }
    
    print("Publishing test configuration...")
    response = requests.post(f"{BASE_URL}/config/publish", json=data, headers=headers)
    response.raise_for_status()
    result = response.json()
    print(f"Configuration published! Version: {result.get('version')}")
    return result

def start_embedding(token, config_id):
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "config_id": config_id,
        "batch_size": 10,
        "max_concurrent": 2
    }
    print("Starting embedding job...")
    response = requests.post(f"{BASE_URL}/embedding-jobs", json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def main():
    print("--- Setting up Test Embedding ---")
    token = login()
    print("Logged in.")
    
    conn = get_first_connection(token)
    print(f"Using connection: {conn['name']} (ID: {conn['id']})")
    
    # Fetch connection schema to pick a valid table if 'users' doesn't exist?
    # For now, we'll try a generic publish. If table doesn't exist, generation might fail but job will start.
    
    config = publish_test_config(token, conn['id'])
    
    # We need to get the config ID. The publish endpoint returns {status, version, config_id} ideally.
    # Let's check api.ts or backend code.
    # backend/services/config_service.py: publish_system_prompt returns result from db_service.publish_system_prompt
    # Checking db_service: usually returns the new row or ID.
    # Let's assume we can fetch the 'active' config metadata to get the ID if publish doesn't return it.
    
    # Actually, we can just fetch active config.
    time.sleep(1)
    response = requests.get(f"{BASE_URL}/config/active-metadata", headers={"Authorization": f"Bearer {token}"})
    if response.status_code == 200:
        active_config = response.json()
        config_id = active_config.get('prompt_id') or active_config.get('id')
        print(f"Active Config ID: {config_id}")
        
        if not config_id:
            print(f"Error: Could not find config ID in response: {active_config.keys()}")
            return
        
        job_result = start_embedding(token, config_id)
        print("\nSUCCESS!")
        print(f"Job Started: {job_result['job_id']}")
        print("Go to the UI to see the progress.")
    else:
        print("Failed to fetch active config.")

if __name__ == "__main__":
    main()
