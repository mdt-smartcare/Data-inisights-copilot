"""
Standardized error codes for API responses.
Single source of truth: shared/constants.json
"""
import json
from pathlib import Path

# Load error codes from shared JSON file
_constants_path = Path(__file__).parent.parent.parent / "shared" / "constants.json"
with open(_constants_path) as f:
    _constants = json.load(f)

_error_codes = _constants["errorCodes"]


class ErrorCode:
    """Error codes used in API responses for programmatic handling."""
    
    USER_INACTIVE = _error_codes["USER_INACTIVE"]
    TOKEN_EXPIRED = _error_codes["TOKEN_EXPIRED"]
    TOKEN_INVALID = _error_codes["TOKEN_INVALID"]
    PERMISSION_DENIED = _error_codes["PERMISSION_DENIED"]
    INSUFFICIENT_ROLE = _error_codes["INSUFFICIENT_ROLE"]
    NOT_FOUND = _error_codes["NOT_FOUND"]
    ALREADY_EXISTS = _error_codes["ALREADY_EXISTS"]
    VALIDATION_ERROR = _error_codes["VALIDATION_ERROR"]
    INVALID_INPUT = _error_codes["INVALID_INPUT"]
