import pytest
from eval.retrieval.retrieval_evaluator import RetrievalEvaluator

class TestRetrievalMetrics:
    
    def test_hit_rate(self):
        evaluator = RetrievalEvaluator()
        
        # Query 1: relevant doc retrieved at rank 1 (Hit)
        # Query 2: relevant doc not retrieved (Miss)
        # Query 3: relevant doc retrieved at rank 3 (Hit)
        retrieved = [
            ["doc_A", "doc_B", "doc_C"],
            ["doc_X", "doc_Y", "doc_Z"],
            ["doc_M", "doc_N", "doc_O"]
        ]
        
        expected = [
            ["doc_A"],       # Hit (rank 1)
            ["doc_W"],       # Miss
            ["doc_Q", "doc_O"] # Hit (doc_O is at rank 3)
        ]
        
        hit_rate = evaluator.calculate_hit_rate(retrieved, expected)
        assert hit_rate == (2.0 / 3.0)  # 2 hits out of 3 queries
        
    def test_mrr(self):
        evaluator = RetrievalEvaluator()
        
        retrieved = [
            ["doc_A", "doc_B", "doc_C"], # Expected doc_A -> rank 1 -> MRR = 1.0
            ["doc_X", "doc_Y", "doc_Z"], # Expected doc_Y -> rank 2 -> MRR = 0.5
            ["doc_M", "doc_N", "doc_O"]  # Expected doc_P -> rank None -> MRR = 0.0
        ]
        
        expected = [
            ["doc_A"],
            ["doc_Y"],
            ["doc_P"]
        ]
        
        mrr = evaluator.calculate_mrr(retrieved, expected)
        assert abs(mrr - ((1.0 + 0.5 + 0.0) / 3)) < 1e-5
        
    def test_precision_at_k(self):
        evaluator = RetrievalEvaluator()
        
        retrieved = [
            ["doc_A", "doc_B", "doc_C", "doc_D"],
        ]
        
        # 2 relevant docs in top 4
        expected = [
            ["doc_A", "doc_C", "doc_E"]
        ]
        
        p_at_2 = evaluator.calculate_precision_at_k(retrieved, expected, k=2)
        assert p_at_2 == 0.5  # doc_A is relevant, doc_B is not (1/2)
        
        p_at_4 = evaluator.calculate_precision_at_k(retrieved, expected, k=4)
        assert p_at_4 == 0.5  # doc_A, doc_C relevant out of 4 (2/4)
