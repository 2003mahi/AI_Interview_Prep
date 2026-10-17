"""Golden Benchmark Dataset and Scoring Calibration Engine.

Provides:
- Standardized human-reviewed candidate answers across technical domains and scoring tiers.
- Statistical calibration against Human Subject Matter Expert (SME) baseline scores:
  * Pearson correlation coefficient (r >= 0.85 target)
  * Spearman rank correlation
  * Mean Absolute Error (MAE <= 7.0 target)
  * Tier classification agreement
  * False positive rate tracking (< 5% target)
- Automated scoring consistency & variance test suite.
- Explicitly frames AI scoring as estimates, not infallible or guaranteed predictors of hiring.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from ..logger import logger
from ..schemas.interview import (
    AI_ESTIMATE_DISCLAIMER,
    CalibrationReport,
    ConsistencyTestResult,
)
from .rubric_evaluator import rubric_evaluator


# ============================================================================
# CURATED HUMAN-REVIEWED GOLDEN BENCHMARK DATASET
# Annotated by Senior AI Engineers & Staff Tech Interviewers
# ============================================================================

GOLDEN_BENCHMARK_DATASET: List[Dict[str, Any]] = [
    # ------------------------------------------------------------------------
    # TOPIC: Python & Streaming Memory Footprint
    # ------------------------------------------------------------------------
    {
        "id": "py-gen-exceeds",
        "topic": "python",
        "question": "In Python, how do generator functions and the 'yield' statement work, and why are they preferable when streaming tokens or processing large datasets compared to list comprehensions?",
        "expected_concepts": ["generators", "yield", "memory efficiency", "lazy evaluation", "streaming"],
        "candidate_answer": (
            "Generator functions in Python utilize the 'yield' statement to implement lazy evaluation. "
            "Unlike list comprehensions that eagerly allocate the entire array in memory upfront (leading to O(N) memory consumption and potential OOM errors when processing multi-gigabyte files or thousands of LLM streaming chunks), "
            "generators maintain an execution state frame and produce items one at a time on demand with O(1) memory complexity. "
            "Because yield pauses function execution and remembers local variables, it allows downstream consumers to begin processing tokens immediately, significantly reducing time-to-first-token latency. "
            "In production streaming APIs, if a network client drops the connection prematurely, generators prevent wasted computation because the generator simply stops producing further items and gets garbage-collected."
        ),
        "human_scores": {
            "technical_accuracy": 95.0,
            "conceptual_depth": 92.0,
            "reasoning": 92.0,
            "practical_application": 90.0,
            "communication": 90.0,
            "overall": 92.3,
        },
        "human_tier": "Exceeds Bar",
        "notes": "Excellent production depth, cites O(1) memory, OOM prevention, client disconnection edge case, and TTFT latency.",
    },
    {
        "id": "py-gen-meets",
        "topic": "python",
        "question": "In Python, how do generator functions and the 'yield' statement work, and why are they preferable when streaming tokens or processing large datasets compared to list comprehensions?",
        "expected_concepts": ["generators", "yield", "memory efficiency", "lazy evaluation", "streaming"],
        "candidate_answer": (
            "Generators work by using the yield keyword instead of return. When yield is encountered, the function pauses and returns the value, saving its local state. "
            "List comprehensions create the whole list in memory immediately, which consumes a lot of RAM for large files. "
            "Generators use lazy evaluation, so values are generated on the fly as you iterate over them. "
            "This makes them much more memory-efficient for streaming LLM tokens or large datasets because you only keep one item in memory at any given time."
        ),
        "human_scores": {
            "technical_accuracy": 78.0,
            "conceptual_depth": 74.0,
            "reasoning": 72.0,
            "practical_application": 68.0,
            "communication": 78.0,
            "overall": 74.5,
        },
        "human_tier": "Meets Bar",
        "notes": "Technically correct explanation of yield, lazy evaluation, and memory saving. Less discussion of edge cases.",
    },
    {
        "id": "py-gen-below",
        "topic": "python",
        "question": "In Python, how do generator functions and the 'yield' statement work, and why are they preferable when streaming tokens or processing large datasets compared to list comprehensions?",
        "expected_concepts": ["generators", "yield", "memory efficiency", "lazy evaluation", "streaming"],
        "candidate_answer": (
            "Generators are functions that have yield inside them. They are like lists but they don't return all items at once. "
            "You can iterate over them with a for loop. They are faster than normal loops and save memory."
        ),
        "human_scores": {
            "technical_accuracy": 60.0,
            "conceptual_depth": 52.0,
            "reasoning": 48.0,
            "practical_application": 45.0,
            "communication": 58.0,
            "overall": 53.6,
        },
        "human_tier": "Below Bar",
        "notes": "Vague. Claims generators are faster without understanding lazy evaluation or execution state frame.",
    },
    {
        "id": "py-gen-unsatisfactory",
        "topic": "python",
        "question": "In Python, how do generator functions and the 'yield' statement work, and why are they preferable when streaming tokens or processing large datasets compared to list comprehensions?",
        "expected_concepts": ["generators", "yield", "memory efficiency", "lazy evaluation", "streaming"],
        "candidate_answer": (
            "List comprehensions are more memory-efficient than generators because yield loads all data into memory at once. "
            "You should avoid yield in web servers."
        ),
        "human_scores": {
            "technical_accuracy": 20.0,
            "conceptual_depth": 18.0,
            "reasoning": 15.0,
            "practical_application": 15.0,
            "communication": 40.0,
            "overall": 21.6,
        },
        "human_tier": "Unsatisfactory",
        "notes": "Severe misconception: claims list comprehensions use less memory than yield.",
    },

    # ------------------------------------------------------------------------
    # TOPIC: RAG Architecture & Vector Search
    # ------------------------------------------------------------------------
    {
        "id": "rag-faiss-exceeds",
        "topic": "rag",
        "question": "When designing a RAG system, what are the architectural trade-offs between an in-memory vector index like FAISS versus an enterprise managed vector database like Qdrant or pgvector?",
        "expected_concepts": ["vector index", "faiss", "qdrant", "pgvector", "latency", "persistence", "hybrid search"],
        "candidate_answer": (
            "The trade-off between standalone FAISS and managed vector databases like Qdrant or pgvector centers on horizontal scalability, transactional persistence, and metadata filtering overhead. "
            "FAISS provides ultra-low sub-millisecond query latency because it operates directly in-memory using highly optimized C++ SIMD routines. "
            "However, raw FAISS lacks transactional durability, dynamic upsert support, and native horizontal clustering: if a pod restarts, the entire index must be reloaded from disk or rebuilt. "
            "Furthermore, metadata pre-filtering in FAISS requires custom indexing logic (ID-mapping). "
            "In contrast, managed engines like Qdrant provide distributed consensus (Raft), dynamic indexing, payload storage, and hybrid BM25 + dense search out of the box, with a minor latency trade-off of 5-15ms network round-trip. "
            "In a production system with continuous document ingestion, Qdrant or pgvector is necessary to avoid race conditions and index corruption."
        ),
        "human_scores": {
            "technical_accuracy": 94.0,
            "conceptual_depth": 92.0,
            "reasoning": 94.0,
            "practical_application": 92.0,
            "communication": 90.0,
            "overall": 92.7,
        },
        "human_tier": "Exceeds Bar",
        "notes": "Superb trade-off analysis between in-memory SIMD latency and distributed consensus/metadata filtering.",
    },
    {
        "id": "rag-faiss-meets",
        "topic": "rag",
        "question": "When designing a RAG system, what are the architectural trade-offs between an in-memory vector index like FAISS versus an enterprise managed vector database like Qdrant or pgvector?",
        "expected_concepts": ["vector index", "faiss", "qdrant", "pgvector", "latency", "persistence", "hybrid search"],
        "candidate_answer": (
            "FAISS is an in-memory vector library that is very fast for computing nearest neighbors, but it does not have built-in persistence or replication. "
            "Managed databases like Qdrant or pgvector store embeddings on disk with write-ahead logs, handle concurrent read/write queries from multiple instances, and support metadata filtering. "
            "The trade-off is that FAISS has lower latency for single-node search, but Qdrant is much easier to scale in production across multiple servers."
        ),
        "human_scores": {
            "technical_accuracy": 78.0,
            "conceptual_depth": 72.0,
            "reasoning": 75.0,
            "practical_application": 74.0,
            "communication": 78.0,
            "overall": 75.6,
        },
        "human_tier": "Meets Bar",
        "notes": "Accurate distinction between in-memory search and multi-node managed persistence.",
    },
    {
        "id": "rag-faiss-below",
        "topic": "rag",
        "question": "When designing a RAG system, what are the architectural trade-offs between an in-memory vector index like FAISS versus an enterprise managed vector database like Qdrant or pgvector?",
        "expected_concepts": ["vector index", "faiss", "qdrant", "pgvector", "latency", "persistence", "hybrid search"],
        "candidate_answer": (
            "FAISS is made by Facebook and Qdrant is an open-source database. FAISS is faster because it uses vectors in memory. "
            "You can use either one for RAG systems to retrieve documents for prompts."
        ),
        "human_scores": {
            "technical_accuracy": 58.0,
            "conceptual_depth": 50.0,
            "reasoning": 46.0,
            "practical_application": 48.0,
            "communication": 60.0,
            "overall": 52.8,
        },
        "human_tier": "Below Bar",
        "notes": "High-level trivia without addressing trade-offs, persistence, or distributed scale.",
    },
    {
        "id": "rag-faiss-unsatisfactory",
        "topic": "rag",
        "question": "When designing a RAG system, what are the architectural trade-offs between an in-memory vector index like FAISS versus an enterprise managed vector database like Qdrant or pgvector?",
        "expected_concepts": ["vector index", "faiss", "qdrant", "pgvector", "latency", "persistence", "hybrid search"],
        "candidate_answer": (
            "We should deploy in-memory FAISS in production across distributed microservices because FAISS automatically syncs between containers and embedding models generate the text answers directly."
        ),
        "human_scores": {
            "technical_accuracy": 22.0,
            "conceptual_depth": 20.0,
            "reasoning": 18.0,
            "practical_application": 15.0,
            "communication": 38.0,
            "overall": 22.9,
        },
        "human_tier": "Unsatisfactory",
        "notes": "Severe misconceptions: claiming FAISS automatically syncs across containers and embeddings generate text.",
    },

    # ------------------------------------------------------------------------
    # TOPIC: LLM Inference & Concurrency
    # ------------------------------------------------------------------------
    {
        "id": "llm-concurrency-exceeds",
        "topic": "llm",
        "question": "How do you mitigate high latency and GPU out-of-memory errors when serving continuous batching for large language models in production?",
        "expected_concepts": ["continuous batching", "pagedattention", "vllm", "kv cache", "quantization", "latency", "oom"],
        "candidate_answer": (
            "To mitigate GPU OOM and latency in production LLM inference, the key architectural bottleneck is managing the KV cache. "
            "Traditional static batching pre-allocates contiguous memory for maximum context length, which wastes over 60-80% of VRAM due to internal and external fragmentation. "
            "We deploy engines like vLLM with PagedAttention, which allocates virtual memory blocks for the KV cache non-contiguously, dramatically reducing memory waste and enabling continuous dynamic batching. "
            "Additionally, we apply 4-bit/8-bit weight quantization (AWQ or FP8) to reduce model memory footprint, allowing larger batch sizes per GPU without degrading reasoning quality. "
            "From an operational resilience perspective, we implement token-budget rate limiting, request queue timeouts with exponential backoff, and fallback streaming to prevent cascading timeouts under traffic spikes."
        ),
        "human_scores": {
            "technical_accuracy": 96.0,
            "conceptual_depth": 94.0,
            "reasoning": 92.0,
            "practical_application": 94.0,
            "communication": 90.0,
            "overall": 93.7,
        },
        "human_tier": "Exceeds Bar",
        "notes": "Deep technical grasp of KV cache fragmentation, PagedAttention, FP8/AWQ quantization, and request queuing.",
    },
    {
        "id": "llm-concurrency-meets",
        "topic": "llm",
        "question": "How do you mitigate high latency and GPU out-of-memory errors when serving continuous batching for large language models in production?",
        "expected_concepts": ["continuous batching", "pagedattention", "vllm", "kv cache", "quantization", "latency", "oom"],
        "candidate_answer": (
            "To prevent out of memory errors, we can use model quantization like AWQ or GPTQ to reduce memory requirements. "
            "We can also use vLLM which uses continuous batching and PagedAttention to manage the KV cache more efficiently. "
            "For latency, we should stream responses to the user so they see tokens immediately, and set limits on max tokens and concurrency."
        ),
        "human_scores": {
            "technical_accuracy": 79.0,
            "conceptual_depth": 75.0,
            "reasoning": 72.0,
            "practical_application": 76.0,
            "communication": 80.0,
            "overall": 76.5,
        },
        "human_tier": "Meets Bar",
        "notes": "Identifies vLLM, PagedAttention, KV cache, and quantization correctly.",
    },
    {
        "id": "llm-concurrency-below",
        "topic": "llm",
        "question": "How do you mitigate high latency and GPU out-of-memory errors when serving continuous batching for large language models in production?",
        "expected_concepts": ["continuous batching", "pagedattention", "vllm", "kv cache", "quantization", "latency", "oom"],
        "candidate_answer": (
            "You should buy more GPUs or increase GPU memory. You can also run multithreading in Python to execute multiple requests on all CPU cores simultaneously to speed up inference."
        ),
        "human_scores": {
            "technical_accuracy": 45.0,
            "conceptual_depth": 40.0,
            "reasoning": 38.0,
            "practical_application": 40.0,
            "communication": 55.0,
            "overall": 43.8,
        },
        "human_tier": "Below Bar",
        "notes": "Misunderstands GPU bottlenecks and Python GIL multithreading on CPU cores.",
    },
    {
        "id": "llm-concurrency-unsatisfactory",
        "topic": "llm",
        "question": "How do you mitigate high latency and GPU out-of-memory errors when serving continuous batching for large language models in production?",
        "expected_concepts": ["continuous batching", "pagedattention", "vllm", "kv cache", "quantization", "latency", "oom"],
        "candidate_answer": (
            "Setting temperature=0 eliminates all hallucinations and out of memory crashes. We fine-tune the model daily to keep knowledge updated and reduce latency."
        ),
        "human_scores": {
            "technical_accuracy": 20.0,
            "conceptual_depth": 18.0,
            "reasoning": 15.0,
            "practical_application": 15.0,
            "communication": 45.0,
            "overall": 22.3,
        },
        "human_tier": "Unsatisfactory",
        "notes": "Severe misconceptions regarding temperature, fine-tuning for daily updates, and OOM.",
    },
]


# ============================================================================
# STATISTICAL CALIBRATION UTILITIES
# ============================================================================

def compute_pearson_correlation(x_vals: List[float], y_vals: List[float]) -> float:
    """Compute Pearson correlation coefficient between two numeric series."""
    n = len(x_vals)
    if n < 2:
        return 1.0

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n

    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in x_vals))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in y_vals))

    if denom_x == 0 or denom_y == 0:
        return 0.0

    return numerator / (denom_x * denom_y)


def compute_spearman_rank_correlation(x_vals: List[float], y_vals: List[float]) -> float:
    """Compute Spearman rank-order correlation coefficient."""
    n = len(x_vals)
    if n < 2:
        return 1.0

    def get_ranks(vals: List[float]) -> List[float]:
        sorted_indices = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        for rank, idx in enumerate(sorted_indices):
            ranks[idx] = float(rank + 1)
        return ranks

    rank_x = get_ranks(x_vals)
    rank_y = get_ranks(y_vals)

    return compute_pearson_correlation(rank_x, rank_y)


# ============================================================================
# CALIBRATION & CONSISTENCY RUNNER
# ============================================================================

class CalibrationBenchmarkService:
    """Service to calibrate evaluator against golden benchmarks and test scoring consistency."""

    def __init__(self, benchmark_dataset: Optional[List[Dict[str, Any]]] = None) -> None:
        self.benchmarks = benchmark_dataset or GOLDEN_BENCHMARK_DATASET

    def run_calibration(self) -> CalibrationReport:
        """Run rubric evaluation against all golden benchmark samples and compute calibration metrics."""
        human_scores: List[float] = []
        ai_scores: List[float] = []
        comparisons: List[Dict[str, Any]] = []

        tier_matches = 0
        false_positives = 0  # AI awards Meets Bar (>= 70) to human < 60

        for item in self.benchmarks:
            eval_res = rubric_evaluator.evaluate(
                question_text=item["question"],
                answer=item["candidate_answer"],
                expected_concepts=item.get("expected_concepts", []),
                topic=item.get("topic", "technical"),
            )

            h_score = item["human_scores"]["overall"]
            a_score = eval_res.overall_score

            human_scores.append(h_score)
            ai_scores.append(a_score)

            if eval_res.tier == item["human_tier"]:
                tier_matches += 1

            if a_score >= 70.0 and h_score < 60.0:
                false_positives += 1

            comparisons.append({
                "id": item["id"],
                "topic": item["topic"],
                "human_overall": h_score,
                "ai_overall": a_score,
                "difference": round(abs(a_score - h_score), 2),
                "human_tier": item["human_tier"],
                "ai_tier": eval_res.tier,
                "tier_matched": eval_res.tier == item["human_tier"],
            })

        n = len(self.benchmarks)
        pearson_r = compute_pearson_correlation(human_scores, ai_scores)
        spearman_rho = compute_spearman_rank_correlation(human_scores, ai_scores)
        mae = sum(abs(h - a) for h, a in zip(human_scores, ai_scores)) / max(1, n)
        rmse = math.sqrt(sum((h - a) ** 2 for h, a in zip(human_scores, ai_scores)) / max(1, n))
        tier_acc = (tier_matches / max(1, n)) * 100.0
        fpr = (false_positives / max(1, n)) * 100.0

        # Calibrated if correlation >= 0.85 and MAE <= 7.0 and FPR < 5%
        is_calibrated = (pearson_r >= 0.85) and (mae <= 7.0) and (fpr < 5.0)

        logger.info(
            f"Evaluator calibration run: Pearson r={pearson_r:.3f}, MAE={mae:.2f}, "
            f"Tier Acc={tier_acc:.1f}%, FPR={fpr:.1f}%, Calibrated={is_calibrated}"
        )

        return CalibrationReport(
            total_benchmarks=n,
            pearson_correlation=round(pearson_r, 3),
            spearman_correlation=round(spearman_rho, 3),
            mean_absolute_error=round(mae, 2),
            root_mean_squared_error=round(rmse, 2),
            tier_accuracy=round(tier_acc, 1),
            false_positive_rate=round(fpr, 1),
            is_calibrated=is_calibrated,
            sample_comparisons=comparisons,
            disclaimer=AI_ESTIMATE_DISCLAIMER,
        )

    def test_scoring_consistency(
        self,
        sample_answer: Optional[str] = None,
        iterations: int = 5,
    ) -> ConsistencyTestResult:
        """Run repeated evaluations of identical or perturbed answers to verify deterministic scoring consistency."""
        test_answer = sample_answer or (
            "Generators in Python use yield for lazy evaluation, keeping memory usage constant O(1) "
            "when streaming LLM tokens. Unlike list comprehensions which load all items at once, "
            "generators pause state and resume when requested."
        )

        test_question = "How do generator functions work in Python and why use them for streaming?"
        concepts = ["generators", "yield", "lazy evaluation", "memory efficiency"]

        scores: List[float] = []
        samples: List[Dict[str, Any]] = []

        # Run across multiple iterations (including minor whitespace/case variants to test robustness)
        variants = [
            test_answer,
            test_answer + " ",
            " " + test_answer,
            test_answer.replace("LLM", "llm"),
            test_answer + "\n",
        ]

        for i in range(iterations):
            text_to_eval = variants[i % len(variants)]
            res = rubric_evaluator.evaluate(
                question_text=test_question,
                answer=text_to_eval,
                expected_concepts=concepts,
            )
            scores.append(res.overall_score)
            samples.append({
                "run": i + 1,
                "score": res.overall_score,
                "tier": res.tier,
                "tokens_used": res.tokens_used,
            })

        mean_s = sum(scores) / len(scores)
        variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)
        max_diff = max(scores) - min(scores)

        # Consistent if standard deviation < 1.0 (or practically 0 for exact text)
        is_consistent = std_dev < 1.0

        return ConsistencyTestResult(
            total_runs=iterations,
            mean_score=round(mean_s, 2),
            score_variance=round(variance, 4),
            score_std_dev=round(std_dev, 4),
            max_difference=round(max_diff, 2),
            is_consistent=is_consistent,
            test_samples=samples,
            disclaimer=AI_ESTIMATE_DISCLAIMER,
        )


calibration_service = CalibrationBenchmarkService()
