"""Interview API Router — Protected Endpoints for Adaptive AI Interviewer.

Provides:
- POST /interview & POST /interview/start: Start an adaptive AI interview session
- POST /interview/{session_id}/answer: Submit candidate answer, receive evaluation & adaptive probes
- GET /interview/{session_id}: Retrieve / resume session state (with cross-user authorization)
- POST /interview/{session_id}/pause: Pause active session
- POST /interview/{session_id}/resume: Resume paused session from exact exit state
- GET /interview/user/sessions: List all sessions for the authenticated user
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...auth import AuthenticatedUser, get_current_user
from ...logger import logger
from ...schemas.interview import (
    CandidateAnswerRequest,
    EvaluationResult,
    GeneratedQuestion,
    InteractionTurn,
    InterviewResponse,
    InterviewRole,
    InterviewSessionState,
    QuestionTopic,
    SessionStatus,
    StartInterviewRequest,
    EvaluateAnswerPayload,
    RubricEvaluationResult,
    CalibrationReport,
    ConsistencyTestResult,
)
from ...services.adaptive_interviewer import adaptive_interviewer
from ...services.interview_repository import interview_repository
from ...services.rubric_evaluator import rubric_evaluator
from ...services.calibration_benchmark import calibration_service


router = APIRouter()


class AdaptiveSessionResponse(BaseModel):
    """Rich session response compatible with both legacy clients and adaptive interface."""
    session_id: str
    user_id: str
    role: str
    status: str
    current_question_index: int
    total_questions: int
    active_question: Optional[GeneratedQuestion] = None
    questions: List[str] = Field(default_factory=list)
    awaiting_probe: bool = False
    average_score: Optional[float] = None
    summary_feedback: Optional[str] = None
    interactions: List[InteractionTurn] = Field(default_factory=list)
    message: Optional[str] = None


def _to_session_response(
    state: InterviewSessionState,
    active_q: Optional[GeneratedQuestion] = None,
    msg: Optional[str] = None,
) -> AdaptiveSessionResponse:
    q_list = [state.current_question.question_text] if state.current_question else []
    if not q_list and state.asked_questions:
        q_list = state.asked_questions

    return AdaptiveSessionResponse(
        session_id=state.session_id,
        user_id=state.user_id,
        role=state.role,
        status=state.status,
        current_question_index=state.current_question_index,
        total_questions=state.total_questions,
        active_question=active_q or state.current_probe or state.current_question,
        questions=q_list,
        awaiting_probe=state.awaiting_probe,
        average_score=state.average_score,
        summary_feedback=state.summary_feedback,
        interactions=state.interactions,
        message=msg,
    )


class GenericStartPayload(BaseModel):
    role: str = "GenAI Engineer"
    experience_years: int = 3
    topics: Optional[List[Any]] = None
    total_questions: int = Field(default=6, ge=1, le=15)


@router.post("/interview", response_model=AdaptiveSessionResponse)
@router.post("/interview/start", response_model=AdaptiveSessionResponse)
async def start_interview_session(
    payload: GenericStartPayload,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Start an adaptive interview session for AI Engineer and GenAI roles.
    Server-side authorization: user_id is assigned strictly from current_user.id.
    """
    if payload.experience_years < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Experience years must be non-negative",
        )

    # Parse and validate topics
    parsed_topics: List[QuestionTopic] = []
    if payload.topics:
        for t in payload.topics:
            t_str = str(t).lower().replace(" ", "_")
            try:
                parsed_topics.append(QuestionTopic(t_str))
            except ValueError:
                # Map non-standard topic strings to technical or general
                parsed_topics.append(QuestionTopic.TECHNICAL)

    start_req = StartInterviewRequest(
        role=payload.role,
        experience_years=payload.experience_years,
        topics=parsed_topics or None,
        total_questions=payload.total_questions,
    )

    state = adaptive_interviewer.start_session(
        user_id=current_user.id,
        request=start_req,
    )

    # Persist session in repository
    await interview_repository.save_session(state)
    logger.info(f"Initialized adaptive interview session {state.session_id} for user {current_user.id}")

    return _to_session_response(state, state.current_question, "Interview session started successfully.")


@router.post("/interview/{session_id}/answer", response_model=InterviewResponse)
async def submit_candidate_answer(
    session_id: str,
    payload: CandidateAnswerRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Submit an answer to the active question or reasoning probe.
    Enforces cross-user access authorization.
    """
    state = await interview_repository.get_session_by_id(session_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found",
        )

    if state.user_id != current_user.id:
        logger.warning(f"Cross-user attempt: {current_user.id} tried answering session {session_id} of {state.user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this resource",
        )

    if state.status == SessionStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This interview session is already completed",
        )

    # Process answer through adaptive engine
    updated_state, response = adaptive_interviewer.submit_answer(state, payload)

    # Record turn in DB if available
    if updated_state.interactions:
        last_turn = updated_state.interactions[-1]
        await interview_repository.record_interaction(session_id, last_turn)

    # Save updated session state
    await interview_repository.save_session(updated_state)

    return response


@router.get("/interview/{session_id}", response_model=AdaptiveSessionResponse)
@router.get("/interview/{session_id}/state", response_model=AdaptiveSessionResponse)
async def get_interview_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieve interview session by ID.
    Enforces cross-user authorization. Allows resuming exactly where the candidate exited.
    """
    state = await interview_repository.get_session_by_id(session_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found",
        )

    if state.user_id != current_user.id:
        logger.warning(f"Cross-user access denied: user {current_user.id} tried accessing session {session_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this resource",
        )

    # Re-evaluate active question if needed
    active_q = state.current_probe if state.awaiting_probe else state.current_question

    return _to_session_response(state, active_q, "Session retrieved successfully.")


@router.post("/interview/{session_id}/pause", response_model=AdaptiveSessionResponse)
async def pause_interview_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Pause an active interview session for later continuation."""
    state = await interview_repository.get_session_by_id(session_id)
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    if state.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    state.status = SessionStatus.PAUSED.value
    await interview_repository.save_session(state)
    logger.info(f"Paused interview session {session_id}")

    return _to_session_response(state, None, "Interview session paused. You can resume anytime.")


@router.post("/interview/{session_id}/resume", response_model=InterviewResponse)
async def resume_interview_session(
    session_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Resume an interview session from the exact exit state."""
    state = await interview_repository.get_session_by_id(session_id)
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")

    if state.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    updated_state, response = adaptive_interviewer.resume_session(state)
    await interview_repository.save_session(updated_state)
    logger.info(f"Resumed interview session {session_id}")

    return response


@router.get("/interview/user/sessions", response_model=List[AdaptiveSessionResponse])
async def list_user_interview_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """List all interview sessions for the current authenticated user."""
    sessions = await interview_repository.list_user_sessions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [_to_session_response(s) for s in sessions]


@router.post("/interview/evaluate", response_model=RubricEvaluationResult)
async def evaluate_candidate_answer(
    payload: EvaluateAnswerPayload,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Evaluate candidate response across 5 core rubric dimensions:
    1. Technical Accuracy (30%)
    2. Conceptual Depth (20%)
    3. Reasoning & Trade-Offs (20%)
    4. Practical Application & Edge Cases (15%)
    5. Communication & Clarity (15%)

    Returns literal evidence quotes, criterion-level feedback, detected misconceptions,
    actionable corrections, and tailored next exercises.
    AI scores are treated as developmental estimates, not guarantees of interview success.
    """
    return rubric_evaluator.evaluate(
        question_text=payload.question_text,
        answer=payload.answer_text,
        expected_concepts=payload.expected_concepts or [],
        topic=payload.topic or "technical",
        role=payload.role or "GenAI Engineer",
        context_or_scenario=payload.context_or_scenario,
    )


@router.get("/interview/evaluation/calibration", response_model=CalibrationReport)
async def get_evaluator_calibration_report(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Retrieve statistical calibration report of AI rubric scores against human SME golden benchmarks.
    Computes Pearson correlation (target >= 0.85), MAE (target <= 7.0), tier accuracy, and false positive rate.
    """
    return calibration_service.run_calibration()


@router.post("/interview/evaluation/consistency-test", response_model=ConsistencyTestResult)
async def run_scoring_consistency_test(
    sample_answer: Optional[str] = None,
    iterations: int = Query(default=5, ge=2, le=20),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Run scoring consistency and determinism tests across repeated iterations or perturbations.
    Validates that score variance is strictly controlled (< 1.0).
    """
    return calibration_service.test_scoring_consistency(
        sample_answer=sample_answer,
        iterations=iterations,
    )

