# eval/pipeline/e2e_evaluator.py
import time
import logging
from typing import List, Dict, Any
from rouge_score import rouge_scorer

logger = logging.getLogger("eval.pipeline")

class EndToEndEvaluator:
    """
    Evaluates the full AgentService pipeline end-to-end.
    Measures total latency, token usage, and ROUGE-L similarity vs ground truth.
    """
    def __init__(self, agent_service):
        """Pass an initialized instance of backend.services.agent_service.AgentService"""
        self.agent_service = agent_service
        self.scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=True)

    async def evaluate_batch(self, queries: List[str], expected_answers: List[str]) -> Dict[str, Any]:
        """
        Run E2E evaluation. Since the agent pipeline is async, this must be awaited.
        """
        if len(queries) != len(expected_answers):
            raise ValueError("Query and expected_answer lists must have same length")

        results = []
        total_latency_ms = 0.0
        total_rouge = 0.0
        
        for idx, (query, expected) in enumerate(zip(queries, expected_answers)):
            logger.info(f"E2E evaluating {idx+1}/{len(queries)}: '{query[:40]}...'")
            
            start = time.time()
            try:
                # Mock a session ID to test context handling if needed, or None for stateless
                response = await self.agent_service.process_query(query=query, session_id=f"eval_session_{idx}")
                
                # The response is a Dict conforming to ChatResponse schema
                actual_answer = response.get("answer", "")
                
                # Calculate ROUGE-L
                score = self.scorer.score(expected, actual_answer)
                rouge_l_f1 = score['rougeL'].fmeasure
                
                total_rouge += rouge_l_f1
                
                # Extract token usage and trace info if available
                trace_id = response.get("trace_id", "unknown")
                
                logger.info(f"  -> ROUGE-L: {rouge_l_f1:.4f} | Trace: {trace_id}")
                
            except Exception as e:
                logger.error(f"E2E execution failed for query: {query}. Error: {e}")
                
            finally:
                latency = (time.time() - start) * 1000
                total_latency_ms += latency
                
        total_queries = len(queries)
        avg_latency = total_latency_ms / total_queries if total_queries > 0 else 0.0
        avg_rouge_l = total_rouge / total_queries if total_queries > 0 else 0.0

        return {
            "avg_latency_ms": avg_latency,
            "avg_rouge_l": avg_rouge_l,
            "queries_processed": total_queries
        }
