"""Rubric-Based Evaluator Service for Technical Interviews.

Evaluates candidate responses across five core dimensions:
1. Technical Accuracy (30%): Correctness of underlying algorithmic, syntax, and architectural concepts.
2. Conceptual Depth (20%): Deep understanding of mechanics vs superficial buzzword recitation.
3. Reasoning (20%): Causal explanations ('why'/'because'), trade-off analysis, and comparative rationale.
4. Practical Application (15%): Production edge-cases, failure modes, concurrency, latency, and resource constraints.
5. Communication (15%): Structure, conciseness, precision, and absence of filler/rambling.

Features:
- Returns evidence quotes grounded strictly in candidate answers.
- Identifies specific technical misconceptions and provides actionable corrections.
- Recommends tailored next exercises based on detected gaps.
- Highly token/credit efficient: deterministic rule-calibrated scoring engine (zero-token/zero-cost)
  with optional compact LLM evaluation fallback.
- Explicitly treats AI scores as estimates rather than guaranteed predictions of interview success.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config import settings
from ..logger import logger
from ..schemas.interview import (
    AI_ESTIMATE_DISCLAIMER,
    CriterionLevelFeedback,
    DifficultyLevel,
    GeneratedQuestion,
    MisconceptionItem,
    NextExerciseItem,
    QuestionTopic,
    RubricDimension,
    RubricDimensionScore,
    RubricEvaluationResult,
)


# ============================================================================
# RUBRIC WEIGHTS & OPERATIONAL ANCHORS
# ============================================================================

RUBRIC_WEIGHTS: Dict[str, float] = {
    RubricDimension.TECHNICAL_ACCURACY.value: 0.30,
    RubricDimension.CONCEPTUAL_DEPTH.value: 0.20,
    RubricDimension.REASONING.value: 0.20,
    RubricDimension.PRACTICAL_APPLICATION.value: 0.15,
    RubricDimension.COMMUNICATION.value: 0.15,
}

DIMENSION_LABELS: Dict[str, str] = {
    RubricDimension.TECHNICAL_ACCURACY.value: "Technical Accuracy",
    RubricDimension.CONCEPTUAL_DEPTH.value: "Conceptual Depth",
    RubricDimension.REASONING.value: "Reasoning & Trade-Offs",
    RubricDimension.PRACTICAL_APPLICATION.value: "Practical Application & Edge Cases",
    RubricDimension.COMMUNICATION.value: "Communication & Clarity",
}


def score_to_tier(score: float) -> str:
    """Map numeric score (0-100) to operational anchor tier."""
    if score >= 85.0:
        return "Exceeds Bar"
    elif score >= 70.0:
        return "Meets Bar"
    elif score >= 50.0:
        return "Below Bar"
    else:
        return "Unsatisfactory"


# ============================================================================
# KNOWN MISCONCEPTION PATTERNS & CORRECTIONS
# ============================================================================

KNOWN_MISCONCEPTIONS: List[Dict[str, Any]] = [
    {
        "concept": "RAG vs Fine-Tuning Knowledge Update",
        "patterns": [
            r"fine[\s-]?tun(?:ing|e).*(?:frequent|latest|real[\s-]?time|daily|new\s+facts|update\s+knowledge)",
            r"fine[\s-]?tun(?:ing|e).*instead\s+of\s+rag\s+to\s+keep.*updated",
        ],
        "explanation": "Fine-tuning updates model behavior, style, and domain vocabulary, but is prone to catastrophic forgetting and hallucinating out-of-date facts. RAG is the recommended pattern for frequently updated factual data.",
        "correction": "Use RAG (Retrieval-Augmented Generation) with vector or hybrid search for dynamic, frequently changing factual knowledge. Reserve fine-tuning for adapting syntax, formatting, or specialized reasoning patterns.",
        "exercise": {
            "title": "Architecting RAG vs Fine-Tuning for Dynamic Knowledge",
            "difficulty": "mid",
            "description": "Design a hybrid system determining when to route queries to a live vector index vs a domain-fine-tuned model. Detail trade-offs in maintenance, indexing latency, and catastrophic forgetting.",
            "target_skills": ["RAG Architecture", "Model Fine-Tuning", "System Design"],
            "estimated_minutes": 35,
        },
    },
    {
        "concept": "Python GIL and Multi-Threading",
        "patterns": [
            r"(?:thread|threading).*(?:run|parallel|execute).*(?:cpu|multiple\s+cores|across\s+all\s+cores)",
            r"gil.*doesn't\s+matter\s+for\s+cpu",
        ],
        "explanation": "In standard CPython, the Global Interpreter Lock (GIL) prevents multiple native OS threads from executing Python bytecode in parallel on multiple CPU cores.",
        "correction": "For CPU-bound tasks in Python (e.g., tokenization, matrix computations, heavy data transformations), use the `multiprocessing` module or native C/Rust extensions rather than standard threading.",
        "exercise": {
            "title": "Benchmarking Concurrency in CPython: Threads vs Multiprocessing",
            "difficulty": "junior",
            "description": "Implement side-by-side benchmarks executing CPU-intensive hashing and I/O-bound HTTP scraping using threading vs multiprocessing. Profile execution times and CPU core utilization.",
            "target_skills": ["Python GIL", "Multiprocessing", "Performance Profiling"],
            "estimated_minutes": 30,
        },
    },
    {
        "concept": "Temperature and Hallucination Fallacy",
        "patterns": [
            r"temperature\s*(?:=|to\s+)?0.*(?:eliminat|prevent|guarante|no\s+more|stop)\s+(?:all\s+)?hallucination",
            r"setting\s+temperature\s*(?:to\s+)?0\s+makes\s+it\s+100%\s+accurate",
        ],
        "explanation": "Setting temperature to 0 makes generation greedy and deterministic, but does NOT prevent hallucinations. If the model's parametric knowledge is flawed or the context is misleading, it will hallucinate deterministically.",
        "correction": "Mitigate hallucinations through grounded context retrieval (RAG), few-shot verification chains, citation enforcement, and output guardrails, not solely by setting temperature to 0.",
        "exercise": {
            "title": "Building Hallucination Detection & Context Grounding Checks",
            "difficulty": "mid",
            "description": "Create an automated evaluator that cross-references LLM response claims with source chunk sentences, computing faithfulness and factual citation coverage.",
            "target_skills": ["Hallucination Mitigation", "RAG Evaluation", "Faithfulness Metrics"],
            "estimated_minutes": 40,
        },
    },
    {
        "concept": "In-Memory FAISS Distributed Production Limits",
        "patterns": [
            r"(?:use|deploy)\s+(?:in[\s-]?memory\s+)?faiss\s+(?:in|for)\s+(?:production|multi[\s-]?instance|distributed)",
            r"faiss.*automatically\s+(?:sync|scale|distribute)",
        ],
        "explanation": "FAISS is a low-level similarity search library without native horizontal scaling, distributed replication, clustering, or dynamic transactional updates.",
        "correction": "In distributed, high-concurrency production deployments, use a dedicated managed or clustered vector database (e.g., Qdrant, Milvus, pgvector, or Pinecone) or front FAISS with an orchestrated RPC/microservice layer with persistent storage.",
        "exercise": {
            "title": "Migrating from Standalone FAISS to Clustered Vector Storage",
            "difficulty": "senior",
            "description": "Document an architecture migration from a single-node in-memory FAISS index to a fault-tolerant pgvector/Qdrant cluster handling concurrent write-upserts and hybrid search.",
            "target_skills": ["Vector Databases", "High Availability", "Distributed Systems"],
            "estimated_minutes": 45,
        },
    },
    {
        "concept": "Generator vs List Comprehension Memory Footprint",
        "patterns": [
            r"(?:list\s+comprehension|lists?)\s+(?:is|are)\s+more\s+memory[\s-]?efficient\s+than\s+(?:generator|yield)",
            r"yield\s+loads\s+(?:everything|all\s+data)\s+into\s+memory",
        ],
        "explanation": "List comprehensions eagerly instantiate and allocate the entire collection in memory at once. Generator functions and expressions use lazy evaluation, holding only the current element and function state in memory.",
        "correction": "Use generator functions with `yield` or generator expressions `(x for x in data)` when streaming large datasets or LLM tokens to keep memory consumption constant $O(1)$ instead of $O(N)$.",
        "exercise": {
            "title": "Implementing Memory-Efficient Token Streaming with Generators",
            "difficulty": "junior",
            "description": "Refactor a batch-based response transformer into an asynchronous Python generator that yields parsed streaming tokens with bounded memory usage under heavy concurrent load.",
            "target_skills": ["Python Generators", "Memory Optimization", "Streaming APIs"],
            "estimated_minutes": 25,
        },
    },
    {
        "concept": "Embedding Models Generating Text",
        "patterns": [
            r"embedding\s+(?:model|vectors?)\s+(?:will\s+)?generate\s+(?:text|an\s+answer|the\s+response)",
            r"(?:text-embedding-3|sentence-transformers?)\s+(?:generates|writes)\s+the\s+output",
        ],
        "explanation": "Embedding models convert text sequences into fixed-dimensional mathematical vector representations; they do not perform autoregressive sequence-to-sequence text generation.",
        "correction": "Clarify the pipeline separation: embedding models compute dense vector representations for similarity search, while generative LLMs (like GPT-4o, Claude, or Llama) synthesize human-readable text answers from retrieved contexts.",
        "exercise": {
            "title": "Building an End-to-End Modular Vector Search Pipeline",
            "difficulty": "junior",
            "description": "Write a clean script separating embedding generation, cosine similarity scoring, context aggregation, and final LLM generative synthesis with explicit type annotations.",
            "target_skills": ["Embeddings", "Vector Search", "Prompt Engineering"],
            "estimated_minutes": 30,
        },
    },
]


# ============================================================================
# RUBRIC EVALUATOR ENGINE
# ============================================================================

class RubricEvaluator:
    """Rubric-based evaluation engine for candidate technical responses."""

    def __init__(self) -> None:
        self.weights = RUBRIC_WEIGHTS

    def extract_evidence_quotes(self, answer: str, max_quotes: int = 4) -> List[str]:
        """Extract literal sentences or salient clauses from the candidate's answer as evidence."""
        if not answer or not answer.strip():
            return []

        # Split into sentences or clause chunks
        sentences = re.split(r"(?<=[.!?\n])\s+", answer.strip())
        valid_quotes: List[str] = []

        for s in sentences:
            cleaned = s.strip()
            # Retain sentences that contain substantive length and technical terminology
            if len(cleaned.split()) >= 4 and len(cleaned) >= 20:
                # Ensure it's an exact substring
                if cleaned in answer:
                    valid_quotes.append(cleaned)
                    if len(valid_quotes) >= max_quotes:
                        break

        if not valid_quotes and len(answer.strip()) > 0:
            valid_quotes.append(answer.strip()[:100])

        return valid_quotes

    def detect_misconceptions(self, answer: str) -> Tuple[List[MisconceptionItem], List[str], List[NextExerciseItem]]:
        """Detect known technical misconceptions and formulate matching corrections and exercises."""
        detected_misconceptions: List[MisconceptionItem] = []
        corrections: List[str] = []
        exercises: List[NextExerciseItem] = []

        lower_answer = answer.lower()

        for item in KNOWN_MISCONCEPTIONS:
            for pattern in item["patterns"]:
                match = re.search(pattern, lower_answer, re.IGNORECASE)
                if match:
                    # Extract the snippet around the match as detected statement
                    start = max(0, match.start() - 20)
                    end = min(len(answer), match.end() + 20)
                    statement = answer[start:end].strip()

                    detected_misconceptions.append(
                        MisconceptionItem(
                            concept=item["concept"],
                            detected_statement=statement or match.group(0),
                            explanation=item["explanation"],
                        )
                    )
                    corrections.append(item["correction"])
                    ex = item["exercise"]
                    exercises.append(
                        NextExerciseItem(
                            title=ex["title"],
                            difficulty=ex["difficulty"],
                            description=ex["description"],
                            target_skills=ex["target_skills"],
                            estimated_minutes=ex["estimated_minutes"],
                        )
                    )
                    break  # One match per misconception category

        return detected_misconceptions, corrections, exercises

    def _score_technical_accuracy(
        self,
        clean_answer: str,
        expected_concepts: List[str],
        word_count: int,
        misconceptions: List[MisconceptionItem],
    ) -> Tuple[float, str, List[str]]:
        """Evaluate dimension 1: Technical Accuracy (30%)."""
        if word_count < 5:
            return 10.0, "Answer is empty or trivial; no technical accuracy demonstrated.", []

        matched = [c for c in expected_concepts if c.lower() in clean_answer.lower()]
        concept_ratio = len(matched) / max(1, len(expected_concepts)) if expected_concepts else 0.5

        if misconceptions:
            # Severe misconception: human SMEs cap technical accuracy below 30
            score = max(5.0, 30.0 - (len(misconceptions) - 1) * 10.0)
            feedback = f"Significant technical misconceptions detected: {misconceptions[0].concept}. Factual premise is fundamentally inaccurate."
            quotes = [m.detected_statement for m in misconceptions[:2]]
            return round(score, 1), feedback, quotes

        # Base technical accuracy from concept presence and completeness
        raw_score = 45.0 + (concept_ratio * 40.0) + min(15.0, word_count * 0.1)
        if concept_ratio >= 0.8 and word_count >= 50:
            raw_score = max(raw_score, 88.0 + min(8.0, (word_count - 50) * 0.08))

        score = max(15.0, min(98.0, raw_score))
        evidence_quotes = [f"Direct mention of: {c}" for c in matched[:2]]

        if score >= 85:
            feedback = f"High technical accuracy. Accurately incorporated key concepts ({', '.join(matched[:3])}) with zero detected technical flaws."
        elif score >= 70:
            feedback = f"Sound technical accuracy covering core principles ({', '.join(matched[:2]) if matched else 'general mechanisms'}). Minor technical omissions."
        elif score >= 50:
            feedback = f"Basic technical accuracy. Mentioned some concepts but missed essential mechanics ({', '.join([c for c in expected_concepts if c not in matched][:2])})."
        else:
            feedback = "Significant technical inaccuracies or conceptual confusion detected in response."

        return round(score, 1), feedback, evidence_quotes

    def _score_conceptual_depth(
        self,
        clean_answer: str,
        expected_concepts: List[str],
        word_count: int,
        misconceptions: List[MisconceptionItem],
    ) -> Tuple[float, str, List[str]]:
        """Evaluate dimension 2: Conceptual Depth (20%)."""
        if word_count < 5:
            return 10.0, "No conceptual depth shown in brief answer.", []

        if misconceptions:
            return 20.0, "Conceptual depth compromised by fundamental misconceptions.", []

        # Indicators of depth: explaining mechanisms, architecture, internals
        depth_indicators = [
            "mechanism", "underlying", "architecture", "internals", "allocation",
            "amortized", "complexity", "vector space", "cosine similarity", "in-memory",
            "state machine", "lifecycle", "serialization", "deserialization", "concurrency",
            "latency", "throughput", "pagedattention", "kv cache", "chunking", "context window",
            "o(1)", "o(n)", "fragmentation", "simd", "consensus", "raft", "quantization",
        ]
        matched_indicators = [ind for ind in depth_indicators if ind in clean_answer.lower()]

        base_depth = 40.0 + min(40.0, len(matched_indicators) * 12.0) + min(20.0, word_count * 0.15)
        if len(matched_indicators) >= 3 and word_count >= 60:
            base_depth = max(base_depth, 88.0 + min(6.0, len(matched_indicators) * 1.5))

        score = max(15.0, min(96.0, base_depth))
        quotes = [f"Detailed conceptual term: '{ind}'" for ind in matched_indicators[:2]]

        if score >= 85:
            feedback = f"Deep conceptual understanding. Demonstrated strong grasp of underlying architecture and internal mechanisms ({', '.join(matched_indicators[:3])})."
        elif score >= 70:
            feedback = "Adequate conceptual depth. Explains how the mechanism works beyond superficial definitions."
        elif score >= 50:
            feedback = "Superficial conceptual depth. Relies heavily on high-level definitions without unpacking internal mechanics."
        else:
            feedback = "Lacks conceptual depth. Answer is purely superficial or textbook terminology without depth."

        return round(score, 1), feedback, quotes

    def _score_reasoning(
        self,
        clean_answer: str,
        word_count: int,
        misconceptions: List[MisconceptionItem],
    ) -> Tuple[float, str, List[str]]:
        """Evaluate dimension 3: Reasoning & Trade-Offs (20%)."""
        if word_count < 5:
            return 10.0, "No reasoning or trade-offs articulated.", []

        if misconceptions:
            return 18.0, "Flawed causal reasoning rooted in technical misconceptions.", []

        # Indicators of causal reasoning and comparative trade-offs
        reasoning_markers = [
            "because", "therefore", "in order to", "as a result", "consequently",
            "trade-off", "tradeoff", "versus", "vs", "compared to", "on the other hand",
            "drawback", "advantage", "bottleneck", "downside", "mitigate", "unlike",
            "rather than", "instead of", "leads to",
        ]
        found_markers = [m for m in reasoning_markers if m in clean_answer.lower()]

        raw = 35.0 + min(40.0, len(found_markers) * 12.0) + min(25.0, word_count * 0.12)
        if len(found_markers) >= 3 and word_count >= 60:
            raw = max(raw, 88.0 + min(6.0, len(found_markers) * 1.5))

        score = max(15.0, min(96.0, raw))
        quotes = [f"Reasoning marker: '{m}'" for m in found_markers[:2]]

        if score >= 85:
            feedback = f"Exceptional reasoning and trade-off analysis. Thoroughly justified architectural decisions and compared alternatives ({', '.join(found_markers[:3])})."
        elif score >= 70:
            feedback = "Solid reasoning. Articulated clear 'why' behind choices and acknowledged trade-offs."
        elif score >= 50:
            feedback = "Partial reasoning. Stated an approach but did not rigorously justify why alternatives were rejected."
        else:
            feedback = "Absent or weak reasoning. Lacks trade-off awareness, causal explanations, or comparative evaluation."

        return round(score, 1), feedback, quotes

    def _score_practical_application(
        self,
        clean_answer: str,
        word_count: int,
        misconceptions: List[MisconceptionItem],
    ) -> Tuple[float, str, List[str]]:
        """Evaluate dimension 4: Practical Application & Edge Cases (15%)."""
        if word_count < 5:
            return 10.0, "No practical implementation context provided.", []

        if misconceptions:
            return 16.0, "Practical assumptions invalidated by core misconception.", []

        # Indicators of production awareness: edge cases, failure modes, scale, errors
        practical_markers = [
            "production", "scale", "concurrency", "oom", "out of memory", "timeout",
            "retry", "fallback", "monitoring", "latency", "edge case", "failure mode",
            "rate limit", "exponential backoff", "exception", "logging", "distributed",
            "cache invalidation", "leak", "graceful degradation", "disconnect",
            "disconnection", "race condition", "corruption", "client",
        ]
        found_practical = [p for p in practical_markers if p in clean_answer.lower()]

        raw = 35.0 + min(45.0, len(found_practical) * 13.0) + min(20.0, word_count * 0.1)
        if len(found_practical) >= 3 and word_count >= 60:
            raw = max(raw, 88.0 + min(6.0, len(found_practical) * 1.5))

        score = max(15.0, min(96.0, raw))
        quotes = [f"Production consideration: '{p}'" for p in found_practical[:2]]

        if score >= 85:
            feedback = f"Proactive production mindset. Addressed real-world failure modes, concurrency, and edge cases ({', '.join(found_practical[:3])})."
        elif score >= 70:
            feedback = "Good practical awareness. Acknowledges production constraints and typical operational pitfalls."
        elif score >= 50:
            feedback = "Limited practical grounding. Focuses on happy-path execution without anticipating edge cases or failure modes."
        else:
            feedback = "Naive textbook implementation. Ignores production realities such as memory limits, timeouts, and scale."

        return round(score, 1), feedback, quotes

    def _score_communication(
        self,
        clean_answer: str,
        word_count: int,
    ) -> Tuple[float, str, List[str]]:
        """Evaluate dimension 5: Communication & Clarity (15%)."""
        if word_count < 5:
            return 15.0, "Response is too short to evaluate communication structure.", []

        # Indicators: structure, formatting, lists, step-by-step, conciseness
        has_structure = any(
            marker in clean_answer for marker in ["1.", "2.", "-", "*", "First,", "Second,", "Specifically,", "For example", "Unlike", "However"]
        )
        has_runon = word_count > 400  # rambling deduction

        raw = 65.0
        if 40 <= word_count <= 250:
            raw += 22.0  # optimal concise length
        elif word_count > 250:
            raw += 15.0
        else:
            raw += 5.0

        if has_structure:
            raw += 8.0
        if has_runon:
            raw -= 15.0

        score = max(15.0, min(95.0, raw))

        if score >= 85:
            feedback = "Crisp, structured, and professional communication. Directly answers the prompt without fluff."
        elif score >= 70:
            feedback = "Clear communication. Explains ideas effectively with good structure and technical clarity."
        elif score >= 50:
            feedback = "Understandable but unpolished communication. Could be more organized and structured."
        else:
            feedback = "Disorganized or terse response. Needs clearer structure and professional articulation."

        return round(score, 1), feedback, []


    def evaluate(
        self,
        question_text: str,
        answer: str,
        expected_concepts: Optional[List[str]] = None,
        topic: str = "technical",
        role: str = "GenAI Engineer",
        context_or_scenario: Optional[str] = None,
    ) -> RubricEvaluationResult:
        """Run complete 5-dimension rubric evaluation on candidate answer."""
        clean_answer = answer.strip()
        word_count = len(clean_answer.split())
        concepts = expected_concepts or []

        # Adversarial prompt injection defense
        injection_patterns = [
            r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions",
            r"system\s+(?:prompt|override|message)",
            r"disregard\s+(?:the\s+)?(?:rubric|evaluation|scoring|criteria)",
            r"give\s+(?:me\s+)?(?:a\s+)?(?:score\s+of\s+)?100",
            r"<\|im_start\|>|<\|im_end\|>",
            r"\[INST\]|\[/INST\]",
        ]
        detected_injection = any(re.search(p, clean_answer, re.IGNORECASE) for p in injection_patterns)

        if detected_injection:
            logger.warning(f"Adversarial prompt injection pattern detected in answer: '{clean_answer[:80]}...'")
            tech_score, depth_score, reason_score, prac_score, comm_score = 10.0, 10.0, 10.0, 10.0, 10.0
            tech_fb = "Adversarial prompt injection pattern detected. Manipulative instructions are strictly rejected."
            depth_fb = "Response attempts to bypass system instructions rather than demonstrating conceptual depth."
            reason_fb = "No valid technical reasoning provided."
            prac_fb = "Safety guardrail triggered."
            comm_fb = "Adversarial input format rejected."
            raw_evidence = ["Flagged: prompt injection sequence detected in candidate input."]
            misconceptions, corrections, tailored_exercises = [], [], []
            tech_quotes, depth_quotes, reason_quotes, prac_quotes, comm_quotes = [], [], [], [], []
        else:
            # Step 1: Detect misconceptions and formulate corrections
            misconceptions, corrections, tailored_exercises = self.detect_misconceptions(clean_answer)

            # Step 2: Extract literal evidence quotes from candidate text
            raw_evidence = self.extract_evidence_quotes(clean_answer)

            # Step 3: Compute scores across all 5 dimensions
            tech_score, tech_fb, tech_quotes = self._score_technical_accuracy(clean_answer, concepts, word_count, misconceptions)
            depth_score, depth_fb, depth_quotes = self._score_conceptual_depth(clean_answer, concepts, word_count, misconceptions)
            reason_score, reason_fb, reason_quotes = self._score_reasoning(clean_answer, word_count, misconceptions)
            prac_score, prac_fb, prac_quotes = self._score_practical_application(clean_answer, word_count, misconceptions)
            comm_score, comm_fb, comm_quotes = self._score_communication(clean_answer, word_count)


        # Dimension scores map
        dimension_scores: Dict[str, RubricDimensionScore] = {
            RubricDimension.TECHNICAL_ACCURACY.value: RubricDimensionScore(
                dimension=RubricDimension.TECHNICAL_ACCURACY.value,
                dimension_label=DIMENSION_LABELS[RubricDimension.TECHNICAL_ACCURACY.value],
                score=tech_score,
                weight=self.weights[RubricDimension.TECHNICAL_ACCURACY.value],
                tier=score_to_tier(tech_score),
                feedback=tech_fb,
                evidence_quotes=tech_quotes,
            ),
            RubricDimension.CONCEPTUAL_DEPTH.value: RubricDimensionScore(
                dimension=RubricDimension.CONCEPTUAL_DEPTH.value,
                dimension_label=DIMENSION_LABELS[RubricDimension.CONCEPTUAL_DEPTH.value],
                score=depth_score,
                weight=self.weights[RubricDimension.CONCEPTUAL_DEPTH.value],
                tier=score_to_tier(depth_score),
                feedback=depth_fb,
                evidence_quotes=depth_quotes,
            ),
            RubricDimension.REASONING.value: RubricDimensionScore(
                dimension=RubricDimension.REASONING.value,
                dimension_label=DIMENSION_LABELS[RubricDimension.REASONING.value],
                score=reason_score,
                weight=self.weights[RubricDimension.REASONING.value],
                tier=score_to_tier(reason_score),
                feedback=reason_fb,
                evidence_quotes=reason_quotes,
            ),
            RubricDimension.PRACTICAL_APPLICATION.value: RubricDimensionScore(
                dimension=RubricDimension.PRACTICAL_APPLICATION.value,
                dimension_label=DIMENSION_LABELS[RubricDimension.PRACTICAL_APPLICATION.value],
                score=prac_score,
                weight=self.weights[RubricDimension.PRACTICAL_APPLICATION.value],
                tier=score_to_tier(prac_score),
                feedback=prac_fb,
                evidence_quotes=prac_quotes,
            ),
            RubricDimension.COMMUNICATION.value: RubricDimensionScore(
                dimension=RubricDimension.COMMUNICATION.value,
                dimension_label=DIMENSION_LABELS[RubricDimension.COMMUNICATION.value],
                score=comm_score,
                weight=self.weights[RubricDimension.COMMUNICATION.value],
                tier=score_to_tier(comm_score),
                feedback=comm_fb,
                evidence_quotes=comm_quotes,
            ),
        }

        # Step 4: Compute weighted overall score
        overall_score = sum(
            dim.score * dim.weight for dim in dimension_scores.values()
        )
        if misconceptions:
            overall_score = min(overall_score, 32.0)

        overall_score = max(0.0, min(100.0, round(overall_score, 1)))
        tier = score_to_tier(overall_score)


        # Step 5: Criterion-level feedback
        criterion_feedback = CriterionLevelFeedback(
            technical_accuracy=tech_fb,
            conceptual_depth=depth_fb,
            reasoning=reason_fb,
            practical_application=prac_fb,
            communication=comm_fb,
        )

        # Step 6: Identify Strengths & Areas for Growth
        strengths: List[str] = []
        areas_for_growth: List[str] = []

        for dim in dimension_scores.values():
            if dim.score >= 75:
                strengths.append(f"{dim.dimension_label}: {dim.feedback}")
            elif dim.score < 65:
                areas_for_growth.append(f"{dim.dimension_label}: {dim.feedback}")

        if not strengths:
            strengths.append("Demonstrated foundational effort in answering the technical prompt.")
        if not areas_for_growth and overall_score >= 85:
            areas_for_growth.append("Continue practicing end-to-end system stress-testing and exotic failure mode scenarios.")

        # Step 7: Next Exercises Fallbacks if none triggered by misconceptions
        next_exercises = list(tailored_exercises)
        if len(next_exercises) < 2:
            # Add targeted drill based on lowest-scoring dimension
            lowest_dim = min(dimension_scores.values(), key=lambda d: d.score)
            if lowest_dim.dimension == RubricDimension.PRACTICAL_APPLICATION.value:
                next_exercises.append(
                    NextExerciseItem(
                        title="Production Failure-Mode Analysis Drill",
                        difficulty="mid",
                        description=f"Analyze high-load failure scenarios for {topic}: design circuit-breakers, retries, and bounded memory buffers.",
                        target_skills=["Reliability Engineering", "System Resilience", topic],
                        estimated_minutes=30,
                    )
                )
            elif lowest_dim.dimension == RubricDimension.REASONING.value:
                next_exercises.append(
                    NextExerciseItem(
                        title="Trade-Off Matrix & Comparative Architecture Drill",
                        difficulty="mid",
                        description=f"Construct a comparative trade-off matrix evaluating 3 alternative designs for {topic} with quantitative latency/memory trade-offs.",
                        target_skills=["Architecture Evaluation", "Trade-Off Analysis", topic],
                        estimated_minutes=25,
                    )
                )
            else:
                next_exercises.append(
                    NextExerciseItem(
                        title=f"Core Mechanics Deep-Dive in {topic.title()}",
                        difficulty="junior",
                        description=f"Step-by-step code walkthrough of underlying algorithms and memory allocations in {topic}.",
                        target_skills=["Deep Understanding", topic],
                        estimated_minutes=30,
                    )
                )

        return RubricEvaluationResult(
            overall_score=overall_score,
            tier=tier,
            dimension_scores=dimension_scores,
            criterion_feedback=criterion_feedback,
            evidence=raw_evidence,
            misconceptions=misconceptions,
            corrections=corrections,
            next_exercises=next_exercises,
            strengths=strengths,
            areas_for_growth=areas_for_growth,
            disclaimer=AI_ESTIMATE_DISCLAIMER,
            evaluation_mode="rule_calibrated_heuristic",
            tokens_used=0,
        )


# Global evaluator singleton instance
rubric_evaluator = RubricEvaluator()
