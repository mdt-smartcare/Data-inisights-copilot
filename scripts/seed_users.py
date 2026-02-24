"""
DEPRECATED: Seed script to create users with different roles for testing.

With OIDC/Keycloak integration, users should be created in Keycloak admin console.
This script is kept for local development/testing only where Keycloak is not available.

Usage: python scripts/seed_users.py
"""
import sys
import os
import warnings

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.sqliteDb.db import get_db_service

def seed_users():
    warnings.warn(
        "seed_users.py is deprecated. With Keycloak integration, create users via Keycloak admin console. "
        "This script is for local development only.",
        DeprecationWarning,
        stacklevel=2
    )
    
    db = get_db_service()
    
    users = [
        {"username": "super_admin_user", "password": "password123", "role": "super_admin"},
        {"username": "editor_user", "password": "password123", "role": "editor"},
        {"username": "regular_user", "password": "password123", "role": "user"},
        {"username": "viewer_user", "password": "password123", "role": "viewer"},
    ]
    
    print("Seeding users...")
    for user in users:
        try:
            db.create_user(
                username=user["username"],
                password=user["password"],
                role=user["role"],
                email=f"{user['username']}@example.com",
                full_name=user["username"].replace("_", " ").title()
            )
            print(f"Created {user['username']} ({user['role']})")
        except ValueError:
            print(f"User {user['username']} already exists")
        except Exception as e:
            print(f"Error creating {user['username']}: {e}")

if __name__ == "__main__":
    seed_users()
