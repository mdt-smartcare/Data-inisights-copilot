# eval/retrieval/retrieval_evaluator.py
import logging
from typing import List, Set

logger = logging.getLogger("eval.retrieval")

class RetrievalEvaluator:
    """
    Evaluates Retrieval performance independently of LLM generation.
    Computes standard IR metrics: Hit Rate@K, MRR@K, Precision@K.
    """
    
    @staticmethod
    def calculate_hit_rate(retrieved_docs: List[List[str]], expected_docs: List[List[str]]) -> float:
        """
        Hit Rate measures the proportion of queries for which AT LEAST ONE 
        relevant document is retrieved in the top K results.
        
        Args:
            retrieved_docs: Lists of retrieved document IDs per query
            expected_docs: Lists of ground truth relevant document IDs per query
        """
        if not retrieved_docs or not expected_docs:
            return 0.0
            
        hits = 0
        for retrieved, expected in zip(retrieved_docs, expected_docs):
            if not expected:
                continue # Skip queries with no expected docs
                
            expected_set = set(expected)
            retrieved_set = set(retrieved)
            
            if len(expected_set.intersection(retrieved_set)) > 0:
                hits += 1
                
        # Count only queries that had expected docs
        valid_queries = sum(1 for e in expected_docs if len(e) > 0)
        return hits / valid_queries if valid_queries > 0 else 0.0

    @staticmethod
    def calculate_mrr(retrieved_docs: List[List[str]], expected_docs: List[List[str]]) -> float:
        """
        Mean Reciprocal Rank (MRR) measures the rank of the *first* relevant document.
        MRR = 1/Rank. If rank 1 -> 1.0, rank 2 -> 0.5, rank 3 -> 0.33.
        """
        if not retrieved_docs or not expected_docs:
            return 0.0
            
        mrr_sum = 0.0
        valid_queries = 0
        
        for retrieved, expected in zip(retrieved_docs, expected_docs):
            if not expected:
                continue
                
            valid_queries += 1
            expected_set = set(expected)
            
            # Find the reciprocal rank of the FIRST relevant document
            for rank, doc_id in enumerate(retrieved, start=1):
                if doc_id in expected_set:
                    mrr_sum += (1.0 / rank)
                    break
                    
        return mrr_sum / valid_queries if valid_queries > 0 else 0.0

    @staticmethod
    def calculate_precision_at_k(retrieved_docs: List[List[str]], expected_docs: List[List[str]], k: int = 5) -> float:
        """
        Precision@K measures the proportion of retrieved documents in the top K 
        that are actually relevant.
        """
        if not retrieved_docs or not expected_docs:
            return 0.0
            
        precision_sum = 0.0
        valid_queries = 0
        
        for retrieved, expected in zip(retrieved_docs, expected_docs):
            if not expected:
                continue
                
            valid_queries += 1
            expected_set = set(expected)
            
            # Only look at top K
            top_k_retrieved = retrieved[:k]
            
            relevant_count = sum(1 for doc_id in top_k_retrieved if doc_id in expected_set)
            
            # Precision is Num Relevant in Top K / K
            # (If retrieved less than K, divide by actual retrieved count, or max(1, len))
            denominator = len(top_k_retrieved) if len(top_k_retrieved) > 0 else 1
            precision_sum += (relevant_count / denominator)
            
        return precision_sum / valid_queries if valid_queries > 0 else 0.0

    def evaluate(self, retrieved: List[List[str]], expected: List[List[str]], k: int = 5) -> dict:
        """Run all retrieval metrics."""
        return {
            f"hit_rate@{k}": self.calculate_hit_rate(retrieved, expected),
            f"mrr@{k}": self.calculate_mrr(retrieved, expected),
            f"precision@{k}": self.calculate_precision_at_k(retrieved, expected, k),
        }
