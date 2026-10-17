"""Job Readiness Pydantic Schemas.

Defines validated data models for skills, evidence, gaps, priorities, prerequisites,
targeted exercises, scoring breakdowns, and persistence payloads.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GapType(str, Enum):
    MISSING_RESUME_EVIDENCE = "missing_resume_evidence"
    MISSING_KNOWLEDGE = "missing_knowledge"


class PriorityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SkillEvidence(BaseModel):
    skill: str
    sources: List[str] = Field(default_factory=list, description="e.g. ['resume', 'notes', 'demonstrated']")
    evidence_snippets: List[str] = Field(default_factory=list, description="Excerpts demonstrating the skill")
    proficiency_level: str = Field(default="claimed_on_resume", description="demonstrated | noted | claimed_on_resume")


class TargetedExercise(BaseModel):
    skill: str
    title: str
    description: str
    prerequisites: List[str] = Field(default_factory=list)
    estimated_time_minutes: int = 45
    acceptance_criteria: List[str] = Field(default_factory=list)


class GapItem(BaseModel):
    skill: str
    gap_type: GapType
    priority: PriorityLevel
    reason: str
    actionable_recommendation: str
    prerequisites: List[str] = Field(default_factory=list)
    targeted_exercise: Optional[TargetedExercise] = None


class PriorityGroup(BaseModel):
    high: List[str] = Field(default_factory=list)
    medium: List[str] = Field(default_factory=list)
    low: List[str] = Field(default_factory=list)


class ReadinessScoreBreakdown(BaseModel):
    overall_score: float = Field(ge=0.0, le=100.0, description="Overall readiness score (0-100)")
    resume_coverage_score: float = Field(ge=0.0, le=100.0)
    demonstrated_skill_score: float = Field(ge=0.0, le=100.0)
    knowledge_coverage_score: float = Field(ge=0.0, le=100.0)
    summary: str


class JobReadinessAnalysisResult(BaseModel):
    job_title: Optional[str] = "Target Role"
    required_skills: List[str] = Field(default_factory=list)
    evidence: List[SkillEvidence] = Field(default_factory=list)
    missing_resume_evidence: List[GapItem] = Field(
        default_factory=list,
        description="Skills demonstrated or in notes, but absent from resume"
    )
    missing_knowledge: List[GapItem] = Field(
        default_factory=list,
        description="Skills neither on resume nor in learning notes/demonstrations"
    )
    priorities: PriorityGroup = Field(default_factory=PriorityGroup)
    prerequisites_map: Dict[str, List[str]] = Field(default_factory=dict)
    targeted_exercises: List[TargetedExercise] = Field(default_factory=list)
    readiness_score: ReadinessScoreBreakdown


class AnalyzeReadinessRequest(BaseModel):
    resume_text: Optional[str] = None
    job_description_text: Optional[str] = None
    learning_notes_text: Optional[str] = None
    demonstrated_skills_text: Optional[str] = None
    resume_doc_id: Optional[str] = None
    jd_doc_id: Optional[str] = None
    notes_doc_id: Optional[str] = None
    job_title: Optional[str] = "Software Engineer"


class JobReadinessRecord(BaseModel):
    id: str
    user_id: str
    job_title: Optional[str] = None
    overall_score: float
    analysis: JobReadinessAnalysisResult
    created_at: datetime
    updated_at: datetime
