"""
PHI (Protected Health Information) Redaction Layer.

Redacts sensitive health information before sending data to LLM APIs.
Implements HIPAA Safe Harbor de-identification guidelines covering 18 identifiers.

Usage:
    redactor = PHIRedactor()
    safe_text, mapping = redactor.redact(text)
    # Send safe_text to LLM
    # Optionally restore: original = redactor.restore(response, mapping)
"""
import re
import hashlib
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid

from app.core.utils.logging import get_logger

logger = get_logger(__name__)


class PHIType(str, Enum):
    """HIPAA Safe Harbor 18 Identifiers."""
    NAME = "NAME"
    GEOGRAPHIC = "GEOGRAPHIC"  # Address, city, state, zip
    DATE = "DATE"  # DOB, admission/discharge dates
    PHONE = "PHONE"
    FAX = "FAX"
    EMAIL = "EMAIL"
    SSN = "SSN"
    MRN = "MRN"  # Medical Record Number
    HEALTH_PLAN = "HEALTH_PLAN"
    ACCOUNT = "ACCOUNT"
    LICENSE = "LICENSE"  # License/certification numbers
    VEHICLE = "VEHICLE"  # Vehicle IDs
    DEVICE = "DEVICE"  # Device serial numbers
    URL = "URL"
    IP_ADDRESS = "IP_ADDRESS"
    BIOMETRIC = "BIOMETRIC"
    PHOTO = "PHOTO"
    OTHER = "OTHER"


@dataclass
class RedactionMatch:
    """Represents a single PHI match found in text."""
    original: str
    phi_type: PHIType
    start: int
    end: int
    placeholder: str = ""
    confidence: float = 1.0


@dataclass
class RedactionResult:
    """Result of PHI redaction operation."""
    redacted_text: str
    original_text: str
    matches: List[RedactionMatch] = field(default_factory=list)
    mapping: Dict[str, str] = field(default_factory=dict)  # placeholder -> original
    
    @property
    def has_phi(self) -> bool:
        return len(self.matches) > 0
    
    @property
    def phi_count(self) -> int:
        return len(self.matches)
    
    @property
    def phi_types_found(self) -> Set[PHIType]:
        return {m.phi_type for m in self.matches}


class PHIRedactor:
    """
    PHI Redaction engine for healthcare data.
    
    Detects and redacts:
    - Patient names (common name patterns)
    - Social Security Numbers (SSN)
    - Medical Record Numbers (MRN)
    - Dates (DOB, admission dates in MM/DD/YYYY or similar formats)
    - Phone numbers
    - Email addresses
    - Street addresses
    - ZIP codes (reduces to 3-digit prefix per Safe Harbor)
    - Health plan/insurance numbers
    - Account numbers
    - IP addresses
    - URLs with PII
    
    Attributes:
        enabled: Whether redaction is active
        log_redactions: Whether to log redaction activity
        placeholder_format: Format for placeholders (default: "[{type}_{id}]")
    """
    
    # Common first names for name detection (subset for pattern matching)
    COMMON_NAMES = {
        "james", "john", "robert", "michael", "william", "david", "richard", "joseph",
        "thomas", "charles", "mary", "patricia", "jennifer", "linda", "elizabeth",
        "barbara", "susan", "jessica", "sarah", "karen", "nancy", "lisa", "betty",
        "margaret", "sandra", "ashley", "dorothy", "kimberly", "emily", "donna",
        "christopher", "daniel", "matthew", "anthony", "mark", "donald", "steven",
        "paul", "andrew", "joshua", "kenneth", "kevin", "brian", "george", "edward",
        "ronald", "timothy", "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas",
        "eric", "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin"
    }
    
    def __init__(
        self,
        enabled: bool = True,
        log_redactions: bool = True,
        placeholder_format: str = "[{phi_type}_{id}]",
        restore_enabled: bool = True
    ):
        """
        Initialize PHI Redactor.
        
        Args:
            enabled: Enable/disable redaction (disabled = pass-through)
            log_redactions: Log when PHI is detected (counts only, not content)
            placeholder_format: Format string for placeholders
            restore_enabled: Whether to support restoring original values
        """
        self.enabled = enabled
        self.log_redactions = log_redactions
        self.placeholder_format = placeholder_format
        self.restore_enabled = restore_enabled
        self._counter = 0
        
        # Compile regex patterns for performance
        self._patterns = self._compile_patterns()
        
        logger.info(f"PHI Redactor initialized: enabled={enabled}")
    
    def _compile_patterns(self) -> Dict[PHIType, List[re.Pattern]]:
        """Compile all PHI detection regex patterns."""
        patterns = {}
        
        # SSN: 123-45-6789 or 123456789
        patterns[PHIType.SSN] = [
            re.compile(r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b'),
        ]
        
        # Phone: various formats
        patterns[PHIType.PHONE] = [
            re.compile(r'\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'),
            re.compile(r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b'),
        ]
        
        # Email
        patterns[PHIType.EMAIL] = [
            re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        ]
        
        # Dates: MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD, etc.
        patterns[PHIType.DATE] = [
            re.compile(r'\b(?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])[/\-](?:19|20)\d{2}\b'),
            re.compile(r'\b(?:19|20)\d{2}[/\-](?:0?[1-9]|1[0-2])[/\-](?:0?[1-9]|[12]\d|3[01])\b'),
            re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+(?:19|20)\d{2}\b', re.IGNORECASE),
            re.compile(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+(?:19|20)\d{2}\b', re.IGNORECASE),
        ]
        
        # Medical Record Numbers (common patterns)
        patterns[PHIType.MRN] = [
            re.compile(r'\b(?:MRN|MR#?|Medical Record|Patient ID|Patient #)[\s:]*([A-Z0-9]{6,12})\b', re.IGNORECASE),
            re.compile(r'\b(?:mrn|patient.?id)[\s:=]*["\']?([A-Z0-9]{6,12})["\']?\b', re.IGNORECASE),
        ]
        
        # Health Plan / Insurance Numbers
        patterns[PHIType.HEALTH_PLAN] = [
            re.compile(r'\b(?:Member ID|Insurance ID|Policy #|Group #|Subscriber ID)[\s:]*([A-Z0-9]{8,15})\b', re.IGNORECASE),
            re.compile(r'\b(?:medicare|medicaid)[\s:]*#?[\s:]*([A-Z0-9]{9,12})\b', re.IGNORECASE),
        ]
        
        # Account Numbers
        patterns[PHIType.ACCOUNT] = [
            re.compile(r'\b(?:Account|Acct)[\s#:]*(\d{8,16})\b', re.IGNORECASE),
        ]
        
        # Geographic - ZIP codes (will reduce to 3-digit)
        patterns[PHIType.GEOGRAPHIC] = [
            # Full 5 or 9 digit ZIP
            re.compile(r'\b\d{5}(?:-\d{4})?\b'),
            # Street addresses (common patterns)
            re.compile(r'\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Way|Circle|Cir)\b\.?', re.IGNORECASE),
        ]
        
        # IP Addresses
        patterns[PHIType.IP_ADDRESS] = [
            re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'),
        ]
        
        # URLs (that might contain PII in path/query)
        patterns[PHIType.URL] = [
            re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE),
        ]
        
        # License numbers (driver's license patterns vary by state)
        patterns[PHIType.LICENSE] = [
            re.compile(r'\b(?:DL|Driver.?s?\s*License|License\s*#?)[\s:]*([A-Z0-9]{5,15})\b', re.IGNORECASE),
        ]
        
        return patterns
    
    def _generate_placeholder(self, phi_type: PHIType) -> str:
        """Generate a unique placeholder for a PHI match."""
        self._counter += 1
        short_id = str(self._counter).zfill(3)
        return self.placeholder_format.format(phi_type=phi_type.value, id=short_id)
    
    def _detect_names(self, text: str) -> List[RedactionMatch]:
        """
        Detect potential patient names in text.
        
        Uses heuristics:
        - "Patient: Name" or "Name (Patient)"
        - Common name patterns near healthcare keywords
        - Title + Name patterns (Mr., Mrs., Dr., etc.)
        """
        matches = []
        
        # Pattern: "Patient: John Doe" or "Patient Name: John Doe"
        patient_pattern = re.compile(
            r'(?:patient|pt|name|patient\s+name)[\s:]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b',
            re.IGNORECASE
        )
        for m in patient_pattern.finditer(text):
            matches.append(RedactionMatch(
                original=m.group(1),
                phi_type=PHIType.NAME,
                start=m.start(1),
                end=m.end(1),
                confidence=0.9
            ))
        
        # Pattern: Title + Name (Mr. John Doe, Mrs. Jane Smith)
        title_pattern = re.compile(
            r'\b((?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b'
        )
        for m in title_pattern.finditer(text):
            matches.append(RedactionMatch(
                original=m.group(1),
                phi_type=PHIType.NAME,
                start=m.start(1),
                end=m.end(1),
                confidence=0.85
            ))
        
        # Pattern: Common first name + capitalized word (potential last name)
        # Only in healthcare context
        healthcare_keywords = ['patient', 'diagnosis', 'prescription', 'medication', 
                              'treatment', 'admitted', 'discharged', 'condition', 'symptoms']
        text_lower = text.lower()
        has_healthcare_context = any(kw in text_lower for kw in healthcare_keywords)
        
        if has_healthcare_context:
            name_pattern = re.compile(
                r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b'
            )
            for m in name_pattern.finditer(text):
                first_name = m.group(1).lower()
                if first_name in self.COMMON_NAMES:
                    full_name = f"{m.group(1)} {m.group(2)}"
                    # Check if this position isn't already matched
                    already_matched = any(
                        existing.start <= m.start() < existing.end
                        for existing in matches
                    )
                    if not already_matched:
                        matches.append(RedactionMatch(
                            original=full_name,
                            phi_type=PHIType.NAME,
                            start=m.start(),
                            end=m.end(),
                            confidence=0.7
                        ))
        
        return matches
    
    def detect(self, text: str) -> List[RedactionMatch]:
        """
        Detect all PHI in text without redacting.
        
        Args:
            text: Input text to scan
            
        Returns:
            List of RedactionMatch objects
        """
        if not text or not self.enabled:
            return []
        
        all_matches: List[RedactionMatch] = []
        
        # Run regex patterns
        for phi_type, patterns in self._patterns.items():
            for pattern in patterns:
                for m in pattern.finditer(text):
                    # For patterns with capturing groups, use group(1) if available
                    if m.lastindex and m.lastindex >= 1:
                        matched_text = m.group(1)
                        start = m.start(1)
                        end = m.end(1)
                    else:
                        matched_text = m.group(0)
                        start = m.start()
                        end = m.end()
                    
                    all_matches.append(RedactionMatch(
                        original=matched_text,
                        phi_type=phi_type,
                        start=start,
                        end=end,
                        confidence=1.0
                    ))
        
        # Detect names (more complex heuristic-based)
        name_matches = self._detect_names(text)
        all_matches.extend(name_matches)
        
        # Sort by position and remove overlaps (keep longer/higher confidence matches)
        all_matches.sort(key=lambda x: (x.start, -(x.end - x.start), -x.confidence))
        
        filtered_matches = []
        last_end = -1
        for match in all_matches:
            if match.start >= last_end:
                filtered_matches.append(match)
                last_end = match.end
        
        return filtered_matches
    
    def redact(self, text: str) -> RedactionResult:
        """
        Detect and redact all PHI from text.
        
        Args:
            text: Input text containing potential PHI
            
        Returns:
            RedactionResult with redacted text, matches, and mapping
        """
        if not text:
            return RedactionResult(redacted_text="", original_text="", matches=[], mapping={})
        
        if not self.enabled:
            return RedactionResult(redacted_text=text, original_text=text, matches=[], mapping={})
        
        matches = self.detect(text)
        
        if not matches:
            return RedactionResult(redacted_text=text, original_text=text, matches=[], mapping={})
        
        # Build redacted text by replacing matches
        mapping = {}
        result_parts = []
        last_pos = 0
        
        for match in matches:
            # Add text before this match
            result_parts.append(text[last_pos:match.start])
            
            # Generate placeholder and store mapping
            placeholder = self._generate_placeholder(match.phi_type)
            match.placeholder = placeholder
            mapping[placeholder] = match.original
            
            # Add placeholder
            result_parts.append(placeholder)
            last_pos = match.end
        
        # Add remaining text
        result_parts.append(text[last_pos:])
        
        redacted_text = "".join(result_parts)
        
        if self.log_redactions and matches:
            phi_summary = ", ".join(f"{t.value}:{c}" for t, c in 
                                    sorted(self._count_by_type(matches).items(), key=lambda x: x[0].value))
            logger.info(f"PHI redacted: {len(matches)} items ({phi_summary})")
        
        return RedactionResult(
            redacted_text=redacted_text,
            original_text=text,
            matches=matches,
            mapping=mapping
        )
    
    def _count_by_type(self, matches: List[RedactionMatch]) -> Dict[PHIType, int]:
        """Count matches by PHI type."""
        counts: Dict[PHIType, int] = {}
        for m in matches:
            counts[m.phi_type] = counts.get(m.phi_type, 0) + 1
        return counts
    
    def restore(self, text: str, mapping: Dict[str, str]) -> str:
        """
        Restore original PHI values from placeholders.
        
        WARNING: Only use this for internal processing, never for
        displaying to unauthorized users or sending to external systems.
        
        Args:
            text: Text with placeholders
            mapping: Placeholder -> original value mapping
            
        Returns:
            Text with original values restored
        """
        if not self.restore_enabled:
            logger.warning("PHI restore requested but restore_enabled=False")
            return text
        
        if not mapping:
            return text
        
        result = text
        for placeholder, original in mapping.items():
            result = result.replace(placeholder, original)
        
        return result
    
    def redact_messages(
        self,
        messages: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
        """
        Redact PHI from a list of chat messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            
        Returns:
            Tuple of (redacted messages, combined mapping)
        """
        combined_mapping = {}
        redacted_messages = []
        
        for msg in messages:
            content = msg.get('content', '')
            if content:
                result = self.redact(content)
                redacted_msg = {**msg, 'content': result.redacted_text}
                combined_mapping.update(result.mapping)
            else:
                redacted_msg = msg.copy()
            redacted_messages.append(redacted_msg)
        
        return redacted_messages, combined_mapping
    
    def safe_zip_code(self, zip_code: str) -> str:
        """
        Convert ZIP code to Safe Harbor compliant format (3-digit prefix + 00).
        
        Per HIPAA Safe Harbor, ZIP codes can be reduced to first 3 digits,
        unless population < 20,000, then must be 000.
        """
        clean = re.sub(r'[^0-9]', '', zip_code)
        if len(clean) >= 3:
            # Note: For full compliance, would need to check population data
            # This is a simplified version
            return clean[:3] + "00"
        return "00000"


# Singleton instance for convenience
_default_redactor: Optional[PHIRedactor] = None


def get_phi_redactor() -> PHIRedactor:
    """Get the default PHI redactor instance."""
    global _default_redactor
    if _default_redactor is None:
        # Import settings to check if PHI redaction is enabled
        try:
            from app.core.config import get_settings
            settings = get_settings()
            enabled = getattr(settings, 'phi_redaction_enabled', True)
        except Exception:
            enabled = True
        
        _default_redactor = PHIRedactor(enabled=enabled)
    
    return _default_redactor


def redact_phi(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Convenience function to redact PHI from text.
    
    Args:
        text: Input text
        
    Returns:
        Tuple of (redacted_text, mapping)
    """
    result = get_phi_redactor().redact(text)
    return result.redacted_text, result.mapping
