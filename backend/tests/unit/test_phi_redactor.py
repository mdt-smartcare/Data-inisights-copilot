"""
Unit tests for PHI Redaction Layer.

Tests the detection and redaction of Protected Health Information (PHI)
according to HIPAA Safe Harbor guidelines.
"""
import pytest
from app.core.utils.phi_redactor import (
    PHIRedactor,
    PHIType,
    RedactionResult,
    RedactionMatch,
    get_phi_redactor,
    redact_phi
)


class TestPHIDetection:
    """Test PHI pattern detection."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False)
    
    def test_detect_ssn_with_dashes(self, redactor):
        """Should detect SSN in XXX-XX-XXXX format."""
        text = "Patient SSN is 123-45-6789"
        matches = redactor.detect(text)
        
        assert len(matches) >= 1
        ssn_matches = [m for m in matches if m.phi_type == PHIType.SSN]
        assert len(ssn_matches) == 1
        assert ssn_matches[0].original == "123-45-6789"
    
    def test_detect_ssn_without_dashes(self, redactor):
        """Should detect SSN in XXXXXXXXX format."""
        text = "SSN: 123456789"
        matches = redactor.detect(text)
        
        ssn_matches = [m for m in matches if m.phi_type == PHIType.SSN]
        assert len(ssn_matches) == 1
    
    def test_detect_phone_number(self, redactor):
        """Should detect various phone number formats."""
        text = "Call me at (555) 123-4567 or 555-123-4567"
        matches = redactor.detect(text)
        
        phone_matches = [m for m in matches if m.phi_type == PHIType.PHONE]
        assert len(phone_matches) >= 1
    
    def test_detect_email(self, redactor):
        """Should detect email addresses."""
        text = "Contact: john.doe@hospital.org"
        matches = redactor.detect(text)
        
        email_matches = [m for m in matches if m.phi_type == PHIType.EMAIL]
        assert len(email_matches) == 1
        assert "john.doe@hospital.org" in email_matches[0].original
    
    def test_detect_date_mm_dd_yyyy(self, redactor):
        """Should detect dates in MM/DD/YYYY format."""
        text = "DOB: 01/15/1985"
        matches = redactor.detect(text)
        
        date_matches = [m for m in matches if m.phi_type == PHIType.DATE]
        assert len(date_matches) == 1
    
    def test_detect_date_yyyy_mm_dd(self, redactor):
        """Should detect dates in YYYY-MM-DD format."""
        text = "Admitted: 2024-03-15"
        matches = redactor.detect(text)
        
        date_matches = [m for m in matches if m.phi_type == PHIType.DATE]
        assert len(date_matches) == 1
    
    def test_detect_date_spelled_out(self, redactor):
        """Should detect spelled out dates."""
        text = "Born on January 15, 1985"
        matches = redactor.detect(text)
        
        date_matches = [m for m in matches if m.phi_type == PHIType.DATE]
        assert len(date_matches) == 1
    
    def test_detect_mrn(self, redactor):
        """Should detect Medical Record Numbers."""
        text = "MRN: ABC123456"
        matches = redactor.detect(text)
        
        mrn_matches = [m for m in matches if m.phi_type == PHIType.MRN]
        assert len(mrn_matches) == 1
    
    def test_detect_ip_address(self, redactor):
        """Should detect IP addresses."""
        text = "User logged in from 192.168.1.100"
        matches = redactor.detect(text)
        
        ip_matches = [m for m in matches if m.phi_type == PHIType.IP_ADDRESS]
        assert len(ip_matches) == 1
    
    def test_detect_zip_code(self, redactor):
        """Should detect ZIP codes."""
        text = "Lives in area 90210"
        matches = redactor.detect(text)
        
        geo_matches = [m for m in matches if m.phi_type == PHIType.GEOGRAPHIC]
        assert len(geo_matches) >= 1
    
    def test_detect_street_address(self, redactor):
        """Should detect street addresses."""
        text = "Patient address: 123 Main Street"
        matches = redactor.detect(text)
        
        geo_matches = [m for m in matches if m.phi_type == PHIType.GEOGRAPHIC]
        assert len(geo_matches) >= 1
    
    def test_detect_patient_name(self, redactor):
        """Should detect patient names."""
        text = "Patient: John Smith"
        matches = redactor.detect(text)
        
        name_matches = [m for m in matches if m.phi_type == PHIType.NAME]
        assert len(name_matches) >= 1
    
    def test_detect_name_with_title(self, redactor):
        """Should detect names with titles."""
        text = "Mr. Robert Johnson called today"
        matches = redactor.detect(text)
        
        name_matches = [m for m in matches if m.phi_type == PHIType.NAME]
        assert len(name_matches) >= 1


class TestPHIRedaction:
    """Test PHI redaction functionality."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False)
    
    def test_redact_replaces_phi_with_placeholders(self, redactor):
        """Redaction should replace PHI with placeholders."""
        text = "Patient SSN: 123-45-6789"
        result = redactor.redact(text)
        
        assert result.has_phi
        assert "123-45-6789" not in result.redacted_text
        assert "[SSN_" in result.redacted_text
    
    def test_redact_creates_mapping(self, redactor):
        """Redaction should create a mapping for restoration."""
        text = "Email: test@example.com"
        result = redactor.redact(text)
        
        assert len(result.mapping) > 0
        # Mapping should contain placeholder -> original
        assert any("test@example.com" in v for v in result.mapping.values())
    
    def test_redact_multiple_phi_items(self, redactor):
        """Should redact multiple PHI items in one text."""
        text = "Patient John Smith, SSN 123-45-6789, DOB 01/15/1985"
        result = redactor.redact(text)
        
        assert result.phi_count >= 2  # SSN and date at minimum
        assert "123-45-6789" not in result.redacted_text
        assert "01/15/1985" not in result.redacted_text
    
    def test_redact_preserves_non_phi_text(self, redactor):
        """Redaction should preserve non-PHI text."""
        text = "The diagnosis is diabetes. SSN: 123-45-6789"
        result = redactor.redact(text)
        
        assert "diagnosis is diabetes" in result.redacted_text
    
    def test_redact_empty_text(self, redactor):
        """Should handle empty text gracefully."""
        result = redactor.redact("")
        
        assert result.redacted_text == ""
        assert not result.has_phi
    
    def test_redact_no_phi(self, redactor):
        """Should return original text when no PHI found."""
        text = "This is a normal sentence without PHI."
        result = redactor.redact(text)
        
        assert result.redacted_text == text
        assert not result.has_phi


class TestPHIRestoration:
    """Test PHI restoration functionality."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False, restore_enabled=True)
    
    def test_restore_replaces_placeholders(self, redactor):
        """Restoration should replace placeholders with original values."""
        original = "Patient SSN: 123-45-6789"
        result = redactor.redact(original)
        
        restored = redactor.restore(result.redacted_text, result.mapping)
        
        assert "123-45-6789" in restored
    
    def test_restore_with_empty_mapping(self, redactor):
        """Restoration with empty mapping should return unchanged text."""
        text = "Some text"
        restored = redactor.restore(text, {})
        
        assert restored == text
    
    def test_restore_disabled(self):
        """When restore_enabled=False, restore should return unchanged text."""
        redactor = PHIRedactor(enabled=True, log_redactions=False, restore_enabled=False)
        
        original = "Patient SSN: 123-45-6789"
        result = redactor.redact(original)
        
        # Should warn and return unchanged
        restored = redactor.restore(result.redacted_text, result.mapping)
        assert restored == result.redacted_text


class TestPHIRedactorDisabled:
    """Test behavior when PHI redaction is disabled."""
    
    def test_disabled_returns_original_text(self):
        """When disabled, redact should return original text unchanged."""
        redactor = PHIRedactor(enabled=False)
        
        text = "SSN: 123-45-6789"
        result = redactor.redact(text)
        
        assert result.redacted_text == text
        assert not result.has_phi
    
    def test_disabled_detect_returns_empty(self):
        """When disabled, detect should return empty list."""
        redactor = PHIRedactor(enabled=False)
        
        text = "SSN: 123-45-6789"
        matches = redactor.detect(text)
        
        assert len(matches) == 0


class TestRedactMessages:
    """Test message list redaction for LLM calls."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False)
    
    def test_redact_messages_list(self, redactor):
        """Should redact PHI from list of message dicts."""
        messages = [
            {"role": "system", "content": "You are a healthcare assistant."},
            {"role": "user", "content": "Patient John Smith, SSN 123-45-6789"},
            {"role": "assistant", "content": "I understand."}
        ]
        
        redacted, mapping = redactor.redact_messages(messages)
        
        assert len(redacted) == 3
        assert "123-45-6789" not in redacted[1]["content"]
        assert len(mapping) >= 1  # At least SSN should be captured
    
    def test_redact_messages_preserves_roles(self, redactor):
        """Should preserve message roles during redaction."""
        messages = [
            {"role": "user", "content": "SSN: 123-45-6789"}
        ]
        
        redacted, _ = redactor.redact_messages(messages)
        
        assert redacted[0]["role"] == "user"


class TestSafeZipCode:
    """Test Safe Harbor ZIP code conversion."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False)
    
    def test_safe_zip_5_digit(self, redactor):
        """Should convert 5-digit ZIP to 3-digit + 00."""
        result = redactor.safe_zip_code("90210")
        assert result == "90200"
    
    def test_safe_zip_9_digit(self, redactor):
        """Should convert 9-digit ZIP to 3-digit + 00."""
        result = redactor.safe_zip_code("90210-1234")
        assert result == "90200"


class TestGlobalHelpers:
    """Test module-level helper functions."""
    
    def test_get_phi_redactor_singleton(self):
        """get_phi_redactor should return consistent instance."""
        r1 = get_phi_redactor()
        r2 = get_phi_redactor()
        # Should be same instance (singleton)
        assert r1 is r2
    
    def test_redact_phi_helper(self):
        """redact_phi convenience function should work."""
        text = "SSN: 123-45-6789"
        redacted, mapping = redact_phi(text)
        
        assert "123-45-6789" not in redacted
        assert len(mapping) >= 1


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.fixture
    def redactor(self):
        return PHIRedactor(enabled=True, log_redactions=False)
    
    def test_overlapping_patterns(self, redactor):
        """Should handle overlapping pattern matches gracefully."""
        # A phone number could match both phone and some numeric patterns
        text = "Call 555-123-4567"
        result = redactor.redact(text)
        
        # Should not have duplicate redactions for same position
        assert result.redacted_text.count("[PHONE_") <= 1
    
    def test_unicode_text(self, redactor):
        """Should handle unicode characters properly."""
        text = "Patient: José García, SSN 123-45-6789"
        result = redactor.redact(text)
        
        assert "123-45-6789" not in result.redacted_text
    
    def test_multiline_text(self, redactor):
        """Should handle multiline text."""
        text = """
        Patient Name: John Smith
        SSN: 123-45-6789
        Email: john@example.com
        """
        result = redactor.redact(text)
        
        assert "123-45-6789" not in result.redacted_text
        assert "john@example.com" not in result.redacted_text
    
    def test_healthcare_context_improves_name_detection(self, redactor):
        """Names should be detected more reliably in healthcare context."""
        # Without healthcare keywords
        text1 = "Michael Johnson went shopping."
        matches1 = redactor.detect(text1)
        name_matches1 = [m for m in matches1 if m.phi_type == PHIType.NAME]
        
        # With healthcare keywords
        text2 = "Patient Michael Johnson was diagnosed with hypertension."
        matches2 = redactor.detect(text2)
        name_matches2 = [m for m in matches2 if m.phi_type == PHIType.NAME]
        
        # Healthcare context should have higher confidence/more matches
        assert len(name_matches2) >= len(name_matches1)
