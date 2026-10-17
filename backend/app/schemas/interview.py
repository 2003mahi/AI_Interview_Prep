"""Pydantic schemas for Adaptive AI Interviewer.

Defines schemas for:
- Role and Topic enumerations
- Question generation and validation
- Candidate answer submission and reasoning probes
- Evaluation results with structured scoring and feedback
- Full session state tracking and continuation
"""

from enum import Enum
import hashlib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class InterviewRole(str, Enum):
    AI_ENGINEER = "AI Engineer"
    GENAI_ENGINEER = "GenAI Engineer"
    LLM_ENGINEER = "LLM Engineer"
    ML_ENGINEER = "Machine Learning Engineer"
    FULLSTACK_AI = "Full-Stack AI Engineer"


class QuestionTopic(str, Enum):
    PYTHON = "python"
    RAG = "rag"
    LLM = "llm"
    DEBUGGING = "debugging"
    SYSTEM_DESIGN = "system_design"
    TECHNICAL = "technical"


class DifficultyLevel(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


def normalize_question_text(text: str) -> str:
    """Normalize question text for deduplication comparison."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    words = [w for w in cleaned.split() if len(w) > 2]
    return " ".join(words)


def compute_question_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized question."""
    norm = normalize_question_text(text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


class GeneratedQuestion(BaseModel):
    """A single validated question generated for the candidate."""
    question_id: str
    topic: QuestionTopic
    difficulty: DifficultyLevel
    question_text: str
    context_or_scenario: Optional[str] = None
    expected_concepts: List[str] = Field(default_factory=list)
    key_evaluation_criteria: List[str] = Field(default_factory=list)
    is_followup: bool = False
    parent_question_id: Optional[str] = None
    probe_reason: Optional[str] = None

    @field_validator("question_text")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Question text cannot be empty")
        return v.strip()


class StartInterviewRequest(BaseModel):
    """Request to initiate an adaptive interview session."""
    role: str = "GenAI Engineer"
    experience_years: int = 3
    topics: Optional[List[QuestionTopic]] = None
    total_questions: int = Field(default=6, ge=1, le=15)

    @field_validator("experience_years")
    @classmethod
    def validate_experience(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Experience years must be non-negative")
        return v


class CandidateAnswerRequest(BaseModel):
    """Candidate's response to an active question or follow-up probe."""
    session_id: Optional[str] = None
    question_id: str
    answer: str
    is_probe_answer: bool = False

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Answer cannot be empty")
        return v.strip()



class RubricDimension(str, Enum):
    TECHNICAL_ACCURACY = "technical_accuracy"
    CONCEPTUAL_DEPTH = "conceptual_depth"
    REASONING = "reasoning"
    PRACTICAL_APPLICATION = "practical_application"
    COMMUNICATION = "communication"


class RubricDimensionScore(BaseModel):
    """Detailed score for one rubric dimension."""
    dimension: str
    dimension_label: str
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    tier: str
    feedback: str
    evidence_quotes: List[str] = Field(default_factory=list)


class CriterionLevelFeedback(BaseModel):
    """Criterion-level feedback across all five rubric dimensions."""
    technical_accuracy: str
    conceptual_depth: str
    reasoning: str
    practical_application: str
    communication: str


class MisconceptionItem(BaseModel):
    """Specific technical misconception identified in candidate answer."""
    concept: str
    detected_statement: str
    explanation: str


class NextExerciseItem(BaseModel):
    """Targeted practice exercise based on identified weaknesses."""
    title: str
    difficulty: str
    description: str
    target_skills: List[str] = Field(default_factory=list)
    estimated_minutes: int = 30


AI_ESTIMATE_DISCLAIMER = (
    "AI scores and evaluations are developmental estimates designed for deliberate practice, "
    "self-assessment, and skill diagnostics. They are not guaranteed predictions or endorsements "
    "of actual interview outcomes or hiring decisions."
)


class RubricEvaluationResult(BaseModel):
    """Comprehensive rubric-based evaluation result across 5 core dimensions."""
    overall_score: float = Field(ge=0.0, le=100.0)
    tier: str
    dimension_scores: Dict[str, RubricDimensionScore] = Field(default_factory=dict)
    criterion_feedback: CriterionLevelFeedback
    evidence: List[str] = Field(default_factory=list)
    misconceptions: List[MisconceptionItem] = Field(default_factory=list)
    corrections: List[str] = Field(default_factory=list)
    next_exercises: List[NextExerciseItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    areas_for_growth: List[str] = Field(default_factory=list)
    disclaimer: str = AI_ESTIMATE_DISCLAIMER
    evaluation_mode: str = "rule_calibrated_heuristic"
    tokens_used: int = 0


class EvaluationResult(BaseModel):
    """Evaluation of candidate answer with reasoning probe decisions and rubric breakdown."""
    score: float = Field(ge=0.0, le=100.0)
    technical_accuracy: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    depth_score: float = Field(default=70.0, ge=0.0, le=100.0)
    should_probe: bool = False
    probe_reason: Optional[str] = None
    probe_question: Optional[str] = None
    feedback: str
    rubric_evaluation: Optional[RubricEvaluationResult] = None
    evidence: List[str] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    corrections: List[str] = Field(default_factory=list)
    next_exercises: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = AI_ESTIMATE_DISCLAIMER

    @field_validator("score", "depth_score")
    @classmethod
    def clamp_scores(cls, v: float) -> float:
        return max(0.0, min(100.0, round(float(v), 2)))


class EvaluateAnswerPayload(BaseModel):
    """Direct evaluation request payload."""
    question_text: str
    answer_text: str
    expected_concepts: Optional[List[str]] = Field(default_factory=list)
    topic: Optional[str] = "technical"
    role: Optional[str] = "GenAI Engineer"
    context_or_scenario: Optional[str] = None


class CalibrationReport(BaseModel):
    """Statistical calibration report against human SME golden benchmarks."""
    total_benchmarks: int
    pearson_correlation: float
    spearman_correlation: float
    mean_absolute_error: float
    root_mean_squared_error: float
    tier_accuracy: float
    false_positive_rate: float
    is_calibrated: bool
    sample_comparisons: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = AI_ESTIMATE_DISCLAIMER


class ConsistencyTestResult(BaseModel):
    """Scoring consistency test results across repeated runs or perturbations."""
    total_runs: int
    mean_score: float
    score_variance: float
    score_std_dev: float
    max_difference: float
    is_consistent: bool
    test_samples: List[Dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = AI_ESTIMATE_DISCLAIMER



class InteractionTurn(BaseModel):
    """One completed or active question-answer-evaluation turn in the session."""
    id: str
    question_id: str
    topic: str
    question: str
    difficulty: Optional[str] = None
    expected_concepts: List[str] = Field(default_factory=list)
    user_answer: Optional[str] = None
    score: Optional[float] = None
    feedback: Optional[str] = None
    evaluation_details: Optional[Dict[str, Any]] = None
    probe_question: Optional[str] = None
    probe_reason: Optional[str] = None
    probe_answer: Optional[str] = None
    probe_score: Optional[float] = None
    probe_feedback: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class InterviewSessionState(BaseModel):
    """Full persistent state of the adaptive interview session.
    
    Supports pausing, resuming, and continuing from the exact step.
    """
    session_id: str
    user_id: str
    role: str
    experience_years: int
    status: str = SessionStatus.IN_PROGRESS.value
    target_topics: List[QuestionTopic] = Field(
        default_factory=lambda: [
            QuestionTopic.TECHNICAL,
            QuestionTopic.PYTHON,
            QuestionTopic.RAG,
            QuestionTopic.LLM,
            QuestionTopic.DEBUGGING,
            QuestionTopic.SYSTEM_DESIGN,
        ]
    )
    current_question_index: int = 0
    total_questions: int = 6
    current_question: Optional[GeneratedQuestion] = None
    current_probe: Optional[GeneratedQuestion] = None
    awaiting_probe: bool = False
    interactions: List[InteractionTurn] = Field(default_factory=list)
    average_score: Optional[float] = None
    summary_feedback: Optional[str] = None
    asked_questions: List[str] = Field(default_factory=list)
    asked_question_hashes: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InterviewResponse(BaseModel):
    """Unified response returned by start, answer, and resume endpoints."""
    session_id: str
    status: str
    current_question_index: int
    total_questions: int
    is_probe: bool = False
    active_question: Optional[GeneratedQuestion] = None
    evaluation: Optional[EvaluationResult] = None
    average_score: Optional[float] = None
    summary_feedback: Optional[str] = None
    message: Optional[str] = None
