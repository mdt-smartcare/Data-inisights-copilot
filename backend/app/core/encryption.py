"""
Encryption utilities for sensitive data like API keys.

Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
The encryption key is derived from the application's secret key using PBKDF2.

Usage:
    from app.core.encryption import encrypt_value, decrypt_value
    
    encrypted = encrypt_value("my-api-key")
    decrypted = decrypt_value(encrypted)
"""
import base64
import hashlib
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


# Salt for key derivation - should be consistent across app instances
# This is NOT a secret, just adds uniqueness to the key derivation
_ENCRYPTION_SALT = b"data_insights_copilot_ai_models_v1"


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """
    Get or create a Fernet instance using the application's secret key.
    
    The encryption key is derived from SECRET_KEY environment variable
    or falls back to the default development key.
    
    Returns:
        Fernet instance for encryption/decryption
    """
    # Get secret key from environment
    secret_key = os.environ.get(
        "SECRET_KEY", 
        os.environ.get("ENCRYPTION_KEY", "development-secret-key-change-in-production")
    )
    
    # Derive a proper 32-byte key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_ENCRYPTION_SALT,
        iterations=100_000,  # OWASP recommended minimum
        backend=default_backend()
    )
    
    # Derive key and encode for Fernet (requires URL-safe base64)
    derived_key = kdf.derive(secret_key.encode('utf-8'))
    fernet_key = base64.urlsafe_b64encode(derived_key)
    
    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string.
    
    Args:
        plaintext: The string to encrypt
        
    Returns:
        Base64-encoded encrypted string (URL-safe)
        
    Example:
        >>> encrypted = encrypt_value("sk-abc123")
        >>> # encrypted is like: "gAAAAABl..."
    """
    if not plaintext:
        return ""
    
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plaintext.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')


def decrypt_value(encrypted: str) -> Optional[str]:
    """
    Decrypt an encrypted string.
    
    Args:
        encrypted: The encrypted string (from encrypt_value)
        
    Returns:
        The original plaintext, or None if decryption fails
        
    Example:
        >>> decrypted = decrypt_value(encrypted)
        >>> # decrypted == "sk-abc123"
    """
    if not encrypted:
        return None
    
    try:
        fernet = _get_fernet()
        decrypted_bytes = fernet.decrypt(encrypted.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except (InvalidToken, ValueError, TypeError) as e:
        # Log this in production - indicates tampered or corrupted data
        return None


def is_encrypted(value: str) -> bool:
    """
    Check if a value appears to be Fernet-encrypted.
    
    Args:
        value: String to check
        
    Returns:
        True if value looks like Fernet ciphertext
    """
    if not value:
        return False
    
    # Fernet tokens start with 'gAAAAA' (base64-encoded version + timestamp)
    return value.startswith('gAAAAA') and len(value) > 100


def rotate_encryption_key(old_encrypted: str, new_fernet: Optional[Fernet] = None) -> Optional[str]:
    """
    Re-encrypt a value with a new key (for key rotation).
    
    Args:
        old_encrypted: Value encrypted with old key
        new_fernet: New Fernet instance (uses current key if not provided)
        
    Returns:
        Re-encrypted value, or None if decryption fails
    """
    # Decrypt with current key
    plaintext = decrypt_value(old_encrypted)
    if plaintext is None:
        return None
    
    # Re-encrypt (with new key if provided, otherwise current key)
    if new_fernet:
        encrypted_bytes = new_fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    else:
        return encrypt_value(plaintext)


# For testing purposes - invalidate cache if key changes
def _clear_fernet_cache():
    """Clear the cached Fernet instance. For testing only."""
    _get_fernet.cache_clear()
