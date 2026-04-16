import os
import sys

# Add path to fuzzy_matcher module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'app', 'modules', 'chat', 'query')))
from fuzzy_matcher import FuzzyMatcher

def test_fuzzy_matcher():
    print("Testing FuzzyMatcher...")
    matcher = FuzzyMatcher(threshold=0.6)
    
    # Test valid DB values
    db_values = ["Metformin", "Insulin", "Lisinopril", "Atorvastatin"]
    
    # Typos
    test_cases = [
        ("metformn", "Metformin"),
        ("INSULIIN", "Insulin"),
        ("lisinoprl", "Lisinopril"),
        ("unknown", "unknown")  # Should fall back
    ]
    
    for typo_val, expected in test_cases:
        matched = matcher.match_categorical_value(typo_val, db_values)
        if matched != expected:
            print(f"FAILED: {typo_val} matched {matched}, expected {expected}")
        else:
            print(f"SUCCESS: {typo_val} -> {matched}")

if __name__ == "__main__":
    test_fuzzy_matcher()
