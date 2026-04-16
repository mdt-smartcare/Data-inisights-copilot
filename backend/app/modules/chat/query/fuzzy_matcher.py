import difflib
from typing import Optional, List

class FuzzyMatcher:
    """
    Utility to resolve user strings to exact database categorical values using fuzzy matching.
    """

    def __init__(self, threshold: float = 0.6):
        """
        Initialize the FuzzyMatcher.
        
        Args:
            threshold: The similarity threshold (0.0 to 1.0) below which matches are rejected.
        """
        self.threshold = threshold

    def match_categorical_value(self, user_val: str, valid_values: List[str]) -> Optional[str]:
        """
        Find the closest exact database match for a user-provided string.
        
        Args:
            user_val: The user string to match (e.g., "Metformn").
            valid_values: A list of all unique string values for that database column.
            
        Returns:
            The matched string from valid_values, or the original user_val if no good match.
        """
        if not valid_values or not user_val:
            return user_val

        # Handle exact case-insensitive matches first
        user_val_lower = user_val.lower()
        for v in valid_values:
            if v.lower() == user_val_lower:
                return v

        # Then try to find the closest match
        matches = difflib.get_close_matches(
            user_val, 
            valid_values, 
            n=1, 
            cutoff=self.threshold
        )

        # Let's try matching lowercase if normal matching failed
        if not matches:
            valid_lower_map = {v.lower(): v for v in valid_values}
            matches_lower = difflib.get_close_matches(
                user_val_lower,
                list(valid_lower_map.keys()),
                n=1,
                cutoff=self.threshold
            )
            if matches_lower:
                return valid_lower_map[matches_lower[0]]
            
        return matches[0] if matches else user_val
