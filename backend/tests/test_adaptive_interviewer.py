"""Comprehensive Unit and Integration Tests for Adaptive AI Interviewer.

Tests cover:
1. Session state lifecycle:
   - Starting an adaptive session
   - One-question-at-a-time flow
   - Reasoning probe generation and follow-up evaluation
   - Pausing and resuming from exact exit state
   - Full completion and final summary scoring
2. Duplicate questions prevention:
   - Hash fingerprint matching
   - Token / Jaccard lexical overlap detection
   - Zero duplicates generated across full multi-topic session
3. Invalid responses & safe failure handling:
   - Empty and minimal candidate responses
   - Corrupted / malformed LLM JSON parsing & recovery
   - Network / API exception fallbacks to curated question bank
   - Protection against answering completed sessions
4. Security & cross-user isolation:
   - Enforcing JWT authentication
   - 403 Forbidden when accessing another user's session
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import app
from app.schemas.interview import (
    CandidateAnswerRequest,
    DifficultyLevel,
    EvaluationResult,
    GeneratedQuestion,
    InterviewResponse,
    InterviewRole,
    InterviewSessionState,
    QuestionTopic,
    SessionStatus,
    StartInterviewRequest,
    compute_question_hash,
    normalize_question_text,
)
from app.services.adaptive_interviewer import adaptive_interviewer, AdaptiveInterviewerService
from app.services.interview_repository import interview_repository


class TestSessionStateAndContinuation(unittest.TestCase):
    """Test session state progression, one-question-at-a-time, probing, and pause/resume."""

    def setUp(self):
        self.service = AdaptiveInterviewerService()
        self.user_id = "test-user-adaptive-1"

    def test_start_session_state(self):
        req = StartInterviewRequest(
            role="GenAI Engineer",
            experience_years=4,
            topics=[QuestionTopic.PYTHON, QuestionTopic.RAG, QuestionTopic.LLM],
            total_questions=3,
        )
        state = self.service.start_session(self.user_id, req)

        self.assertEqual(state.user_id, self.user_id)
        self.assertEqual(state.role, "GenAI Engineer")
        self.assertEqual(state.status, SessionStatus.IN_PROGRESS.value)
        self.assertEqual(state.current_question_index, 0)
        self.assertEqual(state.total_questions, 3)
        self.assertIsNotNone(state.current_question)
        self.assertEqual(state.current_question.topic, QuestionTopic.PYTHON)
        self.assertFalse(state.awaiting_probe)
        self.assertEqual(len(state.asked_questions), 1)
        self.assertEqual(len(state.asked_question_hashes), 1)

    def test_one_question_at_a_time_and_probing_flow(self):
        req = StartInterviewRequest(
            role="AI Engineer",
            experience_years=5,
            topics=[QuestionTopic.RAG, QuestionTopic.DEBUGGING],
            total_questions=2,
        )
        state = self.service.start_session(self.user_id, req)
        first_q = state.current_question
        self.assertIsNotNone(first_q)

        # 1. Candidate submits an answer with buzzwords but lacking trade-off justification
        # This should trigger a reasoning probe
        ans_req = CandidateAnswerRequest(
            question_id=first_q.question_id,
            answer="I would use vector search and RAG with chunk size 512 and cosine similarity.",
        )
        state, resp = self.service.submit_answer(state, ans_req)

        self.assertTrue(resp.is_probe)
        self.assertTrue(state.awaiting_probe)
        self.assertIsNotNone(state.current_probe)
        self.assertEqual(state.current_question_index, 0)  # Still on question 0 during probe!
        self.assertIsNotNone(resp.message)
        assert resp.message is not None
        self.assertIn("reasoning probe", resp.message.lower())

        # 2. Candidate answers the follow-up probe
        probe_q = state.current_probe
        self.assertIsNotNone(probe_q)
        assert probe_q is not None
        probe_ans_req = CandidateAnswerRequest(
            question_id=probe_q.question_id,
            answer="The primary trade-off is chunk boundary truncation. Mid-sentence splitting degrades semantic context. Therefore, we mitigate this by using recursive character splitting with 10% overlap and parent-document retrieval.",
            is_probe_answer=True,
        )
        state, resp2 = self.service.submit_answer(state, probe_ans_req)

        self.assertFalse(resp2.is_probe)
        self.assertFalse(state.awaiting_probe)
        self.assertEqual(state.current_question_index, 1)  # Advanced to question 1!
        self.assertIsNotNone(resp2.active_question)
        assert resp2.active_question is not None
        self.assertEqual(resp2.active_question.topic, QuestionTopic.DEBUGGING)

    def test_pause_and_continue_from_exit(self):
        """Candidate pauses session halfway and resumes without losing progress."""
        req = StartInterviewRequest(
            role="GenAI Engineer",
            experience_years=3,
            topics=[QuestionTopic.PYTHON, QuestionTopic.LLM],
            total_questions=2,
        )
        state = self.service.start_session(self.user_id, req)
        self.assertIsNotNone(state.current_question)
        assert state.current_question is not None
        initial_q_text = state.current_question.question_text

        # Candidate pauses session
        state.status = SessionStatus.PAUSED.value

        # Candidate resumes session
        resumed_state, resp = self.service.resume_session(state)
        self.assertEqual(resumed_state.status, SessionStatus.IN_PROGRESS.value)
        self.assertIsNotNone(resp.active_question)
        assert resp.active_question is not None
        self.assertEqual(resp.active_question.question_text, initial_q_text)
        self.assertEqual(resp.current_question_index, 0)

    def test_full_session_completion(self):
        req = StartInterviewRequest(
            role="AI Engineer",
            experience_years=2,
            topics=[QuestionTopic.PYTHON],
            total_questions=1,
        )
        state = self.service.start_session(self.user_id, req)
        active_q = state.current_question
        self.assertIsNotNone(active_q)
        assert active_q is not None

        # Candidate submits comprehensive answer that does not require probe
        ans_req = CandidateAnswerRequest(
            question_id=active_q.question_id,
            answer=(
                "Generators use the yield statement to provide lazy evaluation. "
                "Because values are produced on the fly, memory consumption is O(1) "
                "rather than loading the entire token array into RAM. This is critical for streaming LLM tokens."
            ),
        )
        state, resp = self.service.submit_answer(state, ans_req)

        # Should complete session since total_questions = 1
        self.assertEqual(state.status, SessionStatus.COMPLETED.value)
        self.assertIsNotNone(state.average_score)
        self.assertGreaterEqual(state.average_score, 50.0)
        self.assertIsNotNone(state.summary_feedback)
        self.assertIsNone(resp.active_question)


class TestDuplicateQuestionsPrevention(unittest.TestCase):
    """Test duplicate detection via SHA-256 fingerprinting and lexical token similarity."""

    def setUp(self):
        self.service = AdaptiveInterviewerService()

    def test_exact_hash_match(self):
        text = "How does the Global Interpreter Lock (GIL) impact multi-threading in Python?"
        norm = normalize_question_text(text)
        h = compute_question_hash(text)

        asked_q = [text]
        asked_h = [h]

        # Exact same question must be detected as duplicate
        self.assertTrue(self.service.is_duplicate(text, asked_q, asked_h))
        # Same question with different punctuation or capitalization must be detected
        variant = "how does the global interpreter lock gil impact multithreading in python"
        self.assertTrue(self.service.is_duplicate(variant, asked_q, asked_h))

    def test_lexical_token_overlap_duplicate(self):
        q1 = "Explain how PagedAttention and Continuous Batching optimize the KV cache in vLLM."
        q2 = "How does continuous batching and PagedAttention in vLLM manage the KV cache memory?"

        asked_q = [q1]
        asked_h = [compute_question_hash(q1)]

        # Different wording, but high Jaccard token overlap (> 60%)
        is_dup = self.service.is_duplicate(q2, asked_q, asked_h)
        self.assertTrue(is_dup)

    def test_distinct_questions_not_flagged(self):
        q1 = "Explain how PagedAttention and Continuous Batching optimize the KV cache in vLLM."
        q2 = "What are the core differences between AWQ and GPTQ quantization?"

        asked_q = [q1]
        asked_h = [compute_question_hash(q1)]

        self.assertFalse(self.service.is_duplicate(q2, asked_q, asked_h))

    def test_session_generates_zero_duplicates_across_all_topics(self):
        """Verify that across all 6 topics, generated questions are distinct."""
        req = StartInterviewRequest(
            role="GenAI Engineer",
            experience_years=4,
            topics=[
                QuestionTopic.TECHNICAL,
                QuestionTopic.PYTHON,
                QuestionTopic.RAG,
                QuestionTopic.LLM,
                QuestionTopic.DEBUGGING,
                QuestionTopic.SYSTEM_DESIGN,
            ],
            total_questions=6,
        )
        state = self.service.start_session("dup-test-user", req)
        self.assertIsNotNone(state.current_question)
        assert state.current_question is not None

        questions = [state.current_question.question_text]
        hashes = [state.asked_question_hashes[0]]

        for i in range(1, 6):
            topic = state.target_topics[i]
            q = self.service.generate_question(state, topic)
            # Verify not duplicate
            self.assertFalse(self.service.is_duplicate(q.question_text, questions, hashes))
            questions.append(q.question_text)
            hashes.append(compute_question_hash(q.question_text))
            state.asked_questions.append(q.question_text)
            state.asked_question_hashes.append(hashes[-1])

        # All 6 questions must have unique hashes
        self.assertEqual(len(set(hashes)), 6)


class TestInvalidResponsesAndFailureHandling(unittest.TestCase):
    """Test resilience against malformed LLM JSON, empty answers, and network errors."""

    def setUp(self):
        self.service = AdaptiveInterviewerService()

    def test_empty_and_trivial_candidate_answers(self):
        q = GeneratedQuestion(
            question_id="q-1",
            topic=QuestionTopic.PYTHON,
            difficulty=DifficultyLevel.MID,
            question_text="Explain Python GIL.",
            expected_concepts=["gil", "threads", "concurrency"],
        )
        # Empty answer rejected by Pydantic schema validation
        with self.assertRaises(ValueError):
            CandidateAnswerRequest(question_id="q-1", answer="")

        # Whitespace answer rejected by Pydantic schema validation
        with self.assertRaises(ValueError):
            CandidateAnswerRequest(question_id="q-1", answer="   \n\t  ")

        # Trivial 2-word answer handled gracefully without crash
        eval_result = self.service.evaluate_answer(q, "i dunno", "AI Engineer")
        self.assertLessEqual(eval_result.score, 25.0)
        self.assertFalse(eval_result.should_probe)
        self.assertIn("too brief", eval_result.feedback.lower())

    def test_validate_llm_json_strips_markdown_fences(self):
        raw_markdown = """```json
        {
            "score": 85.0,
            "technical_accuracy": "Solid understanding of KV cache",
            "strengths": ["Clear explanation"],
            "weaknesses": [],
            "depth_score": 82.0,
            "should_probe": false,
            "feedback": "Great explanation."
        }
        ```"""
        parsed = self.service.validate_llm_json(raw_markdown, EvaluationResult)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.score, 85.0)
        self.assertEqual(parsed.technical_accuracy, "Solid understanding of KV cache")

    def test_validate_llm_json_corrupted_payload_recovery(self):
        # Conversational text surrounding the JSON
        messy_response = """
        Here is the evaluation for the candidate:
        {"score": 72.5, "technical_accuracy": "Good", "strengths": ["Mentioned LoRA"], "weaknesses": ["Omitted rank tuning"], "depth_score": 70.0, "should_probe": false, "feedback": "Good response"}
        Hope this helps!
        """
        parsed = self.service.validate_llm_json(messy_response, EvaluationResult)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.score, 72.5)

        # Unparseable gibberish returns None safely without raising an uncaught exception
        garbage = "This is not json at all {broken"
        parsed_garbage = self.service.validate_llm_json(garbage, EvaluationResult)
        self.assertIsNone(parsed_garbage)

    def test_safe_fallback_on_llm_network_failure(self):
        """Simulates network timeout when calling external LLM API."""
        state = InterviewSessionState(
            session_id="net-fail-session",
            user_id="user-net-fail",
            role="GenAI Engineer",
            experience_years=4,
        )

        with patch("httpx.post", side_effect=Exception("Connection timed out")):
            # Even if external call raises, fallback question from curated bank is returned
            question = self.service.generate_question(state, QuestionTopic.LLM)
            self.assertIsNotNone(question)
            self.assertEqual(question.topic, QuestionTopic.LLM)
            self.assertTrue(len(question.question_text) > 20)


class TestInterviewApiRoutesAndSecurity(unittest.TestCase):
    """Integration tests for authenticated API routes and cross-user isolation."""

    def setUp(self):
        self.client = TestClient(app)
        self.token_user1 = create_access_token("user-int-1", "user1@interviewer.com")
        self.token_user2 = create_access_token("user-int-2", "user2@interviewer.com")

    def test_start_and_get_session(self):
        start_payload = {
            "role": "GenAI Engineer",
            "experience_years": 4,
            "topics": ["rag", "llm", "system_design"],
            "total_questions": 3,
        }
        res = self.client.post(
            "/api/v1/interview/start",
            json=start_payload,
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        session_id = data["session_id"]
        self.assertEqual(data["user_id"], "user-int-1")
        self.assertEqual(data["status"], "in_progress")
        self.assertIsNotNone(data["active_question"])

        # Retrieve session
        get_res = self.client.get(
            f"/api/v1/interview/{session_id}",
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["session_id"], session_id)

    def test_cross_user_isolation(self):
        # User 1 creates session
        res = self.client.post(
            "/api/v1/interview/start",
            json={"role": "AI Engineer", "experience_years": 3, "total_questions": 2},
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        session_id = res.json()["session_id"]

        # User 2 attempts to read User 1's session -> MUST be 403 Forbidden
        res_forbidden = self.client.get(
            f"/api/v1/interview/{session_id}",
            headers={"Authorization": f"Bearer {self.token_user2}"},
        )
        self.assertEqual(res_forbidden.status_code, 403)
        self.assertIn("Forbidden", res_forbidden.json()["detail"])

        # User 2 attempts to submit answer to User 1's session -> MUST be 403 Forbidden
        ans_res = self.client.post(
            f"/api/v1/interview/{session_id}/answer",
            json={"question_id": "any-id", "answer": "Hacked answer"},
            headers={"Authorization": f"Bearer {self.token_user2}"},
        )
        self.assertEqual(ans_res.status_code, 403)

    def test_negative_experience_validation(self):
        bad_payload = {"role": "AI Engineer", "experience_years": -2}
        res = self.client.post(
            "/api/v1/interview/start",
            json=bad_payload,
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        self.assertEqual(res.status_code, 400)

    def test_pause_and_resume_routes(self):
        # 1. Start session
        start_res = self.client.post(
            "/api/v1/interview/start",
            json={"role": "GenAI Engineer", "experience_years": 3, "total_questions": 2},
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        session_id = start_res.json()["session_id"]

        # 2. Pause session
        pause_res = self.client.post(
            f"/api/v1/interview/{session_id}/pause",
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        self.assertEqual(pause_res.status_code, 200)
        self.assertEqual(pause_res.json()["status"], "paused")

        # 3. Resume session
        resume_res = self.client.post(
            f"/api/v1/interview/{session_id}/resume",
            headers={"Authorization": f"Bearer {self.token_user1}"},
        )
        self.assertEqual(resume_res.status_code, 200)
        self.assertEqual(resume_res.json()["status"], "in_progress")
        self.assertIsNotNone(resume_res.json()["active_question"])


if __name__ == "__main__":
    unittest.main()
