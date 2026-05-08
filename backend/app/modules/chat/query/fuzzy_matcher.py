import difflib
from typing import Optional, List, Dict, Tuple

class FuzzyMatcher:
    """
    Utility for fuzzy matching of:
    - Categorical values (e.g., "Metformn" → "Metformin")
    - Table names (e.g., "patient_tracker" → "patients_tracking")
    - Column names
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
    
    def match_table_name(
        self,
        search_term: str,
        table_names: List[str],
        threshold: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        """
        Find tables that fuzzy-match a search term.
        
        Uses multiple strategies:
        1. Exact substring matching
        2. Word-part matching (e.g., "patient" matches "patient_tracker_gold")
        3. Fuzzy string matching
        
        Args:
            search_term: Term to search for (e.g., "patient_tracker")
            table_names: List of available table names
            threshold: Optional override threshold (default: use instance threshold)
            
        Returns:
            List of (table_name, score) tuples, sorted by score descending
        """
        if not search_term or not table_names:
            return []
        
        thresh = threshold if threshold is not None else self.threshold
        search_lower = search_term.lower().replace("_", " ")
        search_parts = set(search_lower.split())
        
        matches: List[Tuple[str, float]] = []
        
        for table in table_names:
            table_lower = table.lower()
            table_parts = set(table_lower.replace("_", " ").split())
            
            # Strategy 1: Exact match
            if search_lower == table_lower or search_term.lower() == table_lower:
                matches.append((table, 1.0))
                continue
            
            # Strategy 2: Substring match
            if search_lower in table_lower or table_lower in search_lower:
                # Calculate overlap ratio
                overlap = len(search_lower) / len(table_lower)
                score = min(0.95, 0.7 + overlap * 0.25)
                matches.append((table, score))
                continue
            
            # Strategy 3: Word-part matching
            common_parts = search_parts & table_parts
            if common_parts:
                # Score based on how many parts match
                part_score = len(common_parts) / max(len(search_parts), len(table_parts))
                if part_score >= 0.5:
                    matches.append((table, 0.5 + part_score * 0.4))
                    continue
            
            # Strategy 4: Fuzzy string matching
            ratio = difflib.SequenceMatcher(None, search_lower, table_lower).ratio()
            if ratio >= thresh:
                matches.append((table, ratio))
        
        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def match_column_name(
        self,
        search_term: str,
        columns: List[str],
        threshold: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        """
        Find columns that fuzzy-match a search term.
        
        Args:
            search_term: Column name to search for
            columns: List of available column names
            threshold: Optional override threshold
            
        Returns:
            List of (column_name, score) tuples
        """
        # Reuse table matching logic (works for columns too)
        return self.match_table_name(search_term, columns, threshold)
    
    def find_best_match(
        self,
        search_term: str,
        candidates: List[str],
        threshold: Optional[float] = None
    ) -> Optional[str]:
        """
        Find the single best match for a search term.
        
        Args:
            search_term: Term to search for
            candidates: List of candidates
            threshold: Minimum score threshold
            
        Returns:
            Best matching candidate, or None if no match above threshold
        """
        matches = self.match_table_name(search_term, candidates, threshold)
        return matches[0][0] if matches else None
    
    def suggest_alternatives(
        self,
        invalid_name: str,
        valid_names: List[str],
        max_suggestions: int = 3
    ) -> List[str]:
        """
        Suggest alternative names when an invalid name is used.
        
        Useful for error messages like:
        "Table 'patient_tracker' not found. Did you mean: patient_tracker_gold, patient_tracking?"
        
        Args:
            invalid_name: The invalid table/column name
            valid_names: List of valid names
            max_suggestions: Maximum suggestions to return
            
        Returns:
            List of suggested alternatives
        """
        # Use a lower threshold for suggestions
        matches = self.match_table_name(
            invalid_name,
            valid_names,
            threshold=0.4
        )
        
        return [m[0] for m in matches[:max_suggestions]]
