# eval/ragas_eval/ragas_evaluator.py
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

# Provide mock fallback if ragas is not installed (e.g. during CI without deps)
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

from eval.config import EVAL_LLM_MODEL, EVAL_EMBEDDING_MODEL, OPENAI_API_KEY, logger

class RagasEvaluator:
    """
    Evaluates RAG outputs using the RAGAS framework (Faithfulness, Relevancy, Precision, Recall).
    Requires an LLM (OpenAI) to act as a judge.
    """
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        if not self.use_mock and not RAGAS_AVAILABLE:
            raise ImportError(
                "RAGAS dependencies not found. Run: pip install -r eval/requirements-eval.txt"
            )
            
        if not self.use_mock:
            if not OPENAI_API_KEY:
                logger.warning("OPENAI_API_KEY is not set. RAGAS evaluation may fail.")
            
            # Initialize the Judge LLM and Embedding models for RAGAS
            self.judge_llm = ChatOpenAI(
                model_name=EVAL_LLM_MODEL,
                temperature=0.0,
                api_key=OPENAI_API_KEY
            )
            self.judge_embeddings = OpenAIEmbeddings(
                model=EVAL_EMBEDDING_MODEL,
                api_key=OPENAI_API_KEY
            )
            
            self.metrics = [
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ]

    def evaluate_batch(self, 
                       questions: List[str], 
                       answers: List[str], 
                       contexts: List[List[str]], 
                       ground_truths: List[str]) -> Dict[str, Any]:
        """
        Run RAGAS evaluation on a batch of queries.
        
        Args:
            questions: User queries
            answers: Generated answers from the RAG system
            contexts: List of retrieved document texts for each query
            ground_truths: Expected/ideal answers
            
        Returns:
            Dictionary mapping metric names to aggregate scores.
        """
        if len(questions) != len(answers) or len(questions) != len(contexts):
            raise ValueError("All input lists must have the same length.")

        if self.use_mock:
            logger.info("Running MOCK RAGAS evaluation (no API calls)")
            return {
                "faithfulness": 0.85,
                "answer_relevancy": 0.90,
                "context_precision": 0.80,
                "context_recall": 0.75
            }

        # Convert to HuggingFace Dataset format required by RAGAS
        data = {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
        }
        
        # Ground truth is required for context_recall
        if ground_truths and any(ground_truths):
            data["ground_truth"] = ground_truths

        dataset = Dataset.from_dict(data)
        
        logger.info(f"Starting RAGAS evaluation for {len(questions)} queries...")
        result = evaluate(
            dataset=dataset,
            metrics=self.metrics,
            llm=self.judge_llm,
            embeddings=self.judge_embeddings,
            raise_exceptions=False,
        )
        
        logger.info(f"RAGAS Evaluation complete: {result}")
        return result
