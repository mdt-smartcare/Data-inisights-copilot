"""
Test script for SQLite authentication database.
Run this to verify database setup and functionality.
"""
from db import DatabaseService

def test_database():
    print("🔧 Testing SQLite Database Service...")
    
    db = DatabaseService()
    
    # Test 1: Check admin user exists
    print("\n1️⃣ Testing admin user authentication...")
    admin = db.authenticate_user("admin", "admin")
    if admin:
        print(f"✅ Admin login successful: {admin}")
    else:
        print("❌ Admin login failed")
    
    # Test 2: Create a new user
    print("\n2️⃣ Testing user registration...")
    try:
        new_user = db.create_user(
            username="testuser",
            password="testpass123",
            email="test@example.com",
            full_name="Test User"
        )
        print(f"✅ User created: {new_user}")
    except ValueError as e:
        print(f"ℹ️ User already exists: {e}")
    
    # Test 3: Authenticate new user
    print("\n3️⃣ Testing new user authentication...")
    user = db.authenticate_user("testuser", "testpass123")
    if user:
        print(f"✅ User login successful: {user}")
    else:
        print("❌ User login failed")
    
    # Test 4: Test wrong password
    print("\n4️⃣ Testing wrong password...")
    wrong_auth = db.authenticate_user("testuser", "wrongpassword")
    if not wrong_auth:
        print("✅ Correctly rejected wrong password")
    else:
        print("❌ Security issue: accepted wrong password!")
    
    # Test 5: Get user by username
    print("\n5️⃣ Testing get user by username...")
    user_info = db.get_user_by_username("testuser")
    if user_info:
        print(f"✅ User retrieved: {user_info['username']} - {user_info['email']}")
    else:
        print("❌ User not found")
    
    print("\n✨ Database tests completed!")

if __name__ == "__main__":
    test_database()
