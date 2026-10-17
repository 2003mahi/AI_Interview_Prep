"""Job Readiness Analysis API Routes.

Provides endpoints to compare candidate documents, distinguish missing resume evidence
from genuine knowledge gaps, calculate readiness metrics, and persist results in Supabase.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...auth import AuthenticatedUser, get_current_user
from ...logger import logger
from ...schemas.readiness import (
    AnalyzeReadinessRequest,
    JobReadinessRecord,
)
from ...services.document_repository import document_repository
from ...services.job_readiness_analyzer import job_readiness_analyzer
from ...services.readiness_repository import job_readiness_repository

router = APIRouter(prefix="/readiness", tags=["readiness"])


@router.post(
    "/analyze",
    response_model=JobReadinessRecord,
    status_code=status.HTTP_200_OK,
    summary="Analyze job readiness and persist to Supabase",
)
async def analyze_readiness(
    request: AnalyzeReadinessRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Analyze readiness across resume, JD, notes, and demonstrated skills.

    Extracts required skills, detects evidence, separates missing resume evidence
    from missing knowledge, maps prerequisites, generates targeted exercises,
    and persists the validated analysis in Supabase.
    """
    user_id = str(current_user.id)


    # 1. Resolve resume text (either directly from request or via document repository)
    resume_text = request.resume_text or ""
    if request.resume_doc_id:
        doc = await document_repository.get_by_id(request.resume_doc_id)
        if not doc or doc.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resume document '{request.resume_doc_id}' not found or access denied.",
            )
        resume_text = (doc.extracted_text or "") + "\n" + resume_text

    # 2. Resolve job description text
    jd_text = request.job_description_text or ""
    if request.jd_doc_id:
        doc = await document_repository.get_by_id(request.jd_doc_id)
        if not doc or doc.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job description document '{request.jd_doc_id}' not found or access denied.",
            )
        jd_text = (doc.extracted_text or "") + "\n" + jd_text

    # 3. Resolve learning notes text
    notes_text = request.learning_notes_text or ""
    if request.notes_doc_id:
        doc = await document_repository.get_by_id(request.notes_doc_id)
        if not doc or doc.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Learning notes document '{request.notes_doc_id}' not found or access denied.",
            )
        notes_text = (doc.extracted_text or "") + "\n" + notes_text

    demos_text = request.demonstrated_skills_text or ""

    if not jd_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job description text (or jd_doc_id) is required to perform readiness analysis.",
        )

    # 4. Perform analysis
    analysis_result = job_readiness_analyzer.analyze(
        resume_text=resume_text,
        job_description_text=jd_text,
        learning_notes_text=notes_text,
        demonstrated_skills_text=demos_text,
        job_title=request.job_title,
    )

    # 5. Persist to Supabase
    record = await job_readiness_repository.save_analysis(
        user_id=user_id,
        analysis=analysis_result,
        job_title=request.job_title,
    )

    logger.info(
        f"Generated readiness analysis {record.id} for user {user_id}. "
        f"Score: {record.overall_score}%, Gaps: {len(analysis_result.missing_knowledge)} knowledge / {len(analysis_result.missing_resume_evidence)} resume."
    )
    return record


@router.get(
    "/analyses",
    response_model=List[JobReadinessRecord],
    summary="List candidate's historical readiness analyses",
)
async def list_analyses(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieve all readiness analyses belonging to authenticated user."""
    user_id = str(current_user.id)
    return await job_readiness_repository.list_for_user(user_id=user_id, limit=limit, offset=offset)


@router.get(
    "/analyses/{analysis_id}",
    response_model=JobReadinessRecord,
    summary="Get specific readiness analysis by ID",
)
async def get_analysis(
    analysis_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Fetch an analysis record with user ownership check."""
    user_id = str(current_user.id)
    record = await job_readiness_repository.get_by_id(analysis_id)
    if not record or record.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job readiness analysis not found or access denied.",
        )
    return record


@router.delete(
    "/analyses/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a readiness analysis",
)
async def delete_analysis(
    analysis_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Delete an analysis owned by the user."""
    user_id = str(current_user.id)
    record = await job_readiness_repository.get_by_id(analysis_id)
    if not record or record.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job readiness analysis not found or access denied.",
        )
    await job_readiness_repository.delete(analysis_id)
    return None

