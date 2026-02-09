
import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000/api/v1"

async def register_user(username, password, role):
    async with httpx.AsyncClient() as client:
        try:
            # Register
            resp = await client.post(f"{BASE_URL}/auth/register", json={
                "username": username,
                "password": password,
                "role": role
            })
            if resp.status_code == 400 and "already exists" in resp.text:
                print(f"User {username} already exists, proceeding to login.")
            elif resp.status_code != 201:
                print(f"Failed to register {username}: {resp.text}")
                return None
            
            # Login
            resp = await client.post(f"{BASE_URL}/auth/login", json={
                "username": username,
                "password": password
            })
            if resp.status_code != 200:
                print(f"Failed to login {username}: {resp.text}")
                return None
            return resp.json()["access_token"]
        except Exception as e:
            print(f"Error for {username}: {e}")
            return None

async def test_permission(token, role_name, operation_name, method, endpoint, payload=None, expected_status=200):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            if method == "POST":
                resp = await client.post(f"{BASE_URL}{endpoint}", json=payload, headers=headers)
            elif method == "GET":
                resp = await client.get(f"{BASE_URL}{endpoint}", headers=headers)
            
            status_code = resp.status_code
            allowed = status_code != 403
            
            # Special check for 200 vs 403
            success = (status_code == expected_status) or (status_code == 200 and expected_status==200)
            # If we expect 403, success is status_code == 403
            if expected_status == 403:
                success = status_code == 403
            
            print(f"[{role_name}] {operation_name}: {'PASSED' if success else 'FAILED'} (Status: {status_code}, Expected: {expected_status})")
            return success
        except Exception as e:
            print(f"[{role_name}] {operation_name}: ERROR {e}")
            return False

async def run_verification():
    print("Verifying RBAC Implementation...")
    
    # 1. Create Users
    super_admin_token = await register_user("test_super_admin", "password123", "super_admin")
    editor_token = await register_user("test_editor", "password123", "editor")
    viewer_token = await register_user("test_viewer", "password123", "viewer")
    
    if not (super_admin_token and editor_token and viewer_token):
        print("Failed to get tokens for all users. Aborting.")
        return

    # 2. Test Super Admin (Should be allowed)
    print("\n--- Testing Super Admin (Should Allow All) ---")
    await test_permission(super_admin_token, "SUPER_ADMIN", "Generate Prompt", "POST", "/config/generate", {"data_dictionary": "test"}, 200)
    
    # 3. Test Editor (Should be allowed)
    print("\n--- Testing Editor (Should Allow) ---")
    await test_permission(editor_token, "EDITOR", "Generate Prompt", "POST", "/config/generate", {"data_dictionary": "test"}, 200)

    # 4. Test Viewer (Should be forbidden)
    print("\n--- Testing Viewer (Should Forbid) ---")
    await test_permission(viewer_token, "VIEWER", "Generate Prompt", "POST", "/config/generate", {"data_dictionary": "test"}, 403)
    await test_permission(viewer_token, "VIEWER", "Publish Prompt", "POST", "/config/publish", {"prompt_text": "test", "user_id": "test"}, 403)

if __name__ == "__main__":
    asyncio.run(run_verification())
