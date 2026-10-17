"""Unit and Integration Tests for Rubric-Based Evaluator, Calibration, and Consistency.

Verifies:
1. Scoring across 5 core dimensions (Technical Accuracy, Conceptual Depth, Reasoning, Practical Application, Communication).
2. Evidence extraction with exact substring citation.
3. Criterion-level feedback generation.
4. Misconception detection and actionable corrections.
5. Next exercises recommendation based on weaknesses.
6. Strict inclusion of the AI score estimation disclaimer.
7. Calibration against Human SME Golden Benchmarks (Pearson r >= 0.85, MAE <= 7.0, FPR < 5%).
8. Scoring consistency & variance under repeated runs (variance < 1.0).
9. API endpoints: /interview/evaluate, /interview/evaluation/calibration, /interview/evaluation/consistency-test.
"""

import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import create_access_token
from app.schemas.interview import (
    AI_ESTIMATE_DISCLAIMER,
    EvaluateAnswerPayload,
    GeneratedQuestion,
    QuestionTopic,
    RubricDimension,
    RubricEvaluationResult,
)
from app.services.rubric_evaluator import (
    RUBRIC_WEIGHTS,
    RubricEvaluator,
    rubric_evaluator,
    score_to_tier,
)
from app.services.calibration_benchmark import (
    GOLDEN_BENCHMARK_DATASET,
    calibration_service,
    compute_pearson_correlation,
    compute_spearman_rank_correlation,
)
from app.services.adaptive_interviewer import adaptive_interviewer


class TestRubricEvaluator(unittest.TestCase):
    """Test suite for 5-dimension rubric evaluator."""

    def setUp(self) -> None:
        self.evaluator = RubricEvaluator()
        self.client = TestClient(app)
        self.user_token = create_access_token("eval-test-user-123")
        self.auth_headers = {"Authorization": f"Bearer {self.user_token}"}

    def test_rubric_weights_sum_to_one(self) -> None:
        """Verify the 5 rubric dimension weights strictly sum to 1.0 (100%)."""
        total_weight = sum(RUBRIC_WEIGHTS.values())
        self.assertAlmostEqual(total_weight, 1.0, places=4)
        self.assertEqual(len(RUBRIC_WEIGHTS), 5)
        self.assertIn(RubricDimension.TECHNICAL_ACCURACY.value, RUBRIC_WEIGHTS)
        self.assertIn(RubricDimension.CONCEPTUAL_DEPTH.value, RUBRIC_WEIGHTS)
        self.assertIn(RubricDimension.REASONING.value, RUBRIC_WEIGHTS)
        self.assertIn(RubricDimension.PRACTICAL_APPLICATION.value, RUBRIC_WEIGHTS)
        self.assertIn(RubricDimension.COMMUNICATION.value, RUBRIC_WEIGHTS)

    def test_tier_mapping_anchors(self) -> None:
        """Verify operational anchors for tiers."""
        self.assertEqual(score_to_tier(95.0), "Exceeds Bar")
        self.assertEqual(score_to_tier(85.0), "Exceeds Bar")
        self.assertEqual(score_to_tier(84.9), "Meets Bar")
        self.assertEqual(score_to_tier(70.0), "Meets Bar")
        self.assertEqual(score_to_tier(69.9), "Below Bar")
        self.assertEqual(score_to_tier(50.0), "Below Bar")
        self.assertEqual(score_to_tier(49.9), "Unsatisfactory")
        self.assertEqual(score_to_tier(10.0), "Unsatisfactory")

    def test_five_dimensions_scored(self) -> None:
        """Verify evaluator produces scores and feedback for all 5 dimensions."""
        question = "Explain how generator functions and yield optimize memory when streaming tokens."
        answer = (
            "Generator functions in Python use the yield keyword to produce items lazily one at a time. "
            "Unlike list comprehensions that allocate memory for the entire list upfront, generators "
            "maintain an execution state frame with O(1) memory complexity. This prevents OOM errors "
            "in production when streaming large volumes of LLM tokens, and reduces latency."
        )
        concepts = ["generators", "yield", "lazy evaluation", "memory efficiency"]

        res = self.evaluator.evaluate(
            question_text=question,
            answer=answer,
            expected_concepts=concepts,
            topic="python",
        )

        self.assertIsInstance(res, RubricEvaluationResult)
        self.assertEqual(len(res.dimension_scores), 5)

        for dim in [
            RubricDimension.TECHNICAL_ACCURACY.value,
            RubricDimension.CONCEPTUAL_DEPTH.value,
            RubricDimension.REASONING.value,
            RubricDimension.PRACTICAL_APPLICATION.value,
            RubricDimension.COMMUNICATION.value,
        ]:
            self.assertIn(dim, res.dimension_scores)
            dim_score = res.dimension_scores[dim]
            self.assertGreaterEqual(dim_score.score, 0.0)
            self.assertLessEqual(dim_score.score, 100.0)
            self.assertTrue(len(dim_score.feedback) > 0)

        # Overall score check
        self.assertGreaterEqual(res.overall_score, 70.0)
        self.assertIn(res.tier, ["Meets Bar", "Exceeds Bar"])

    def test_evidence_grounding_exact_substring(self) -> None:
        """Verify evidence quotes are literal substrings from the candidate's answer."""
        answer = (
            "We use FAISS for vector search because it offers ultra-fast SIMD search in memory. "
            "However, in high-concurrency production we prefer Qdrant to avoid race conditions."
        )
        res = self.evaluator.evaluate(
            question_text="FAISS vs Qdrant?",
            answer=answer,
            expected_concepts=["faiss", "qdrant", "concurrency"],
        )

        self.assertGreaterEqual(len(res.evidence), 1)
        for quote in res.evidence:
            self.assertIn(quote, answer, f"Cited quote '{quote}' was not a literal substring of answer!")

    def test_misconception_detection_and_corrections(self) -> None:
        """Verify detection of known misconceptions, paired with corrections and exercises."""
        # Answer with GIL misconception and temperature=0 misconception
        flawed_answer = (
            "To speed up CPU-bound model tokenization, we run multithreading in Python to execute "
            "across multiple cores simultaneously. Also setting temperature=0 eliminates all hallucinations."
        )

        res = self.evaluator.evaluate(
            question_text="How do you optimize concurrency and hallucinations in LLMs?",
            answer=flawed_answer,
            expected_concepts=["multiprocessing", "hallucination", "temperature"],
        )

        self.assertGreaterEqual(len(res.misconceptions), 1)
        self.assertGreaterEqual(len(res.corrections), 1)
        self.assertGreaterEqual(len(res.next_exercises), 1)

        misconception_concepts = [m.concept for m in res.misconceptions]
        self.assertTrue(
            any("GIL" in c or "Temperature" in c for c in misconception_concepts),
            f"Expected GIL or Temperature misconception in {misconception_concepts}",
        )

        # Unsatisfactory score cap
        self.assertLess(res.overall_score, 50.0)
        self.assertEqual(res.tier, "Unsatisfactory")

    def test_next_exercises_recommendation(self) -> None:
        """Verify next exercises are generated with complete actionable fields."""
        answer = "I use lists for everything. Yield is confusing to me."
        res = self.evaluator.evaluate(
            question_text="Generators vs Lists",
            answer=answer,
            expected_concepts=["generators", "yield"],
        )

        self.assertGreaterEqual(len(res.next_exercises), 1)
        exercise = res.next_exercises[0]
        self.assertTrue(len(exercise.title) > 0)
        self.assertIn(exercise.difficulty, ["junior", "mid", "senior"])
        self.assertTrue(len(exercise.description) > 0)
        self.assertGreater(exercise.estimated_minutes, 0)

    def test_disclaimer_present(self) -> None:
        """Verify explicit disclaimer treating AI scores as estimates is attached."""
        res = self.evaluator.evaluate(
            question_text="Sample question",
            answer="Sample answer with some concepts and explanation.",
            expected_concepts=["sample"],
        )
        self.assertIn("estimates", res.disclaimer.lower())
        self.assertIn("not guaranteed predictions", res.disclaimer.lower())

    def test_zero_token_efficiency(self) -> None:
        """Verify the rule-calibrated evaluation consumes 0 external API tokens."""
        res = self.evaluator.evaluate(
            question_text="Explain RAG",
            answer="RAG retrieves relevant chunks using dense vector embeddings.",
            expected_concepts=["rag", "embeddings"],
        )
        self.assertEqual(res.tokens_used, 0)
        self.assertEqual(res.evaluation_mode, "rule_calibrated_heuristic")


class TestCalibrationAndConsistency(unittest.TestCase):
    """Test suite for statistical calibration and scoring consistency."""

    def test_golden_benchmark_calibration_metrics(self) -> None:
        """Verify calibration against human SME benchmarks satisfies quality targets:
        - Pearson correlation r >= 0.85
        - Mean Absolute Error MAE <= 7.0 points
        - False Positive Rate < 5.0%
        - is_calibrated == True
        """
        report = calibration_service.run_calibration()

        self.assertGreaterEqual(report.total_benchmarks, 10)
        self.assertGreaterEqual(report.pearson_correlation, 0.85, f"Pearson r={report.pearson_correlation} < 0.85")
        self.assertLessEqual(report.mean_absolute_error, 7.0, f"MAE={report.mean_absolute_error} > 7.0")
        self.assertLess(report.false_positive_rate, 5.0, f"FPR={report.false_positive_rate} >= 5.0%")
        self.assertTrue(report.is_calibrated)
        self.assertIn("estimates", report.disclaimer.lower())

    def test_scoring_consistency_and_low_variance(self) -> None:
        """Verify scoring consistency across repeated evaluations:
        - Score variance < 1.0 (deterministic repeatability)
        - is_consistent == True
        """
        consistency = calibration_service.test_scoring_consistency(iterations=5)

        self.assertTrue(consistency.is_consistent)
        self.assertLess(consistency.score_variance, 1.0)
        self.assertLess(consistency.score_std_dev, 1.0)
        self.assertLess(consistency.max_difference, 1.0)
        self.assertEqual(len(consistency.test_samples), 5)


class TestEvaluatorApiEndpoints(unittest.TestCase):
    """Test suite for evaluation API endpoints."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self.token = create_access_token("api-eval-user")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_direct_evaluate_endpoint(self) -> None:
        """POST /api/v1/interview/evaluate returns structured 5-dimension rubric response."""
        payload = {
            "question_text": "What is the difference between shallow and deep copy in Python?",
            "answer_text": (
                "A shallow copy creates a new compound object and then inserts references into it to the objects found in the original. "
                "A deep copy constructs a new compound object and then recursively inserts copies of the objects found in the original. "
                "In prompt management, modifying a nested dict in a shallow copy can mutate the default template across concurrent requests."
            ),
            "expected_concepts": ["shallow copy", "deep copy", "nested", "references", "mutations"],
            "topic": "python",
            "role": "GenAI Engineer",
        }

        response = self.client.post("/api/v1/interview/evaluate", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("overall_score", data)
        self.assertIn("tier", data)
        self.assertIn("dimension_scores", data)
        self.assertIn("criterion_feedback", data)
        self.assertIn("evidence", data)
        self.assertIn("misconceptions", data)
        self.assertIn("corrections", data)
        self.assertIn("next_exercises", data)
        self.assertIn("disclaimer", data)

        # 5 dimensions checked
        dims = data["dimension_scores"]
        self.assertEqual(len(dims), 5)
        self.assertIn("technical_accuracy", dims)
        self.assertIn("conceptual_depth", dims)
        self.assertIn("reasoning", dims)
        self.assertIn("practical_application", dims)
        self.assertIn("communication", dims)

    def test_calibration_report_endpoint(self) -> None:
        """GET /api/v1/interview/evaluation/calibration returns golden benchmark report."""
        response = self.client.get("/api/v1/interview/evaluation/calibration", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("pearson_correlation", data)
        self.assertGreaterEqual(data["pearson_correlation"], 0.85)
        self.assertIn("mean_absolute_error", data)
        self.assertLessEqual(data["mean_absolute_error"], 7.0)
        self.assertTrue(data["is_calibrated"])
        self.assertIn("disclaimer", data)

    def test_consistency_test_endpoint(self) -> None:
        """POST /api/v1/interview/evaluation/consistency-test returns variance test results."""
        response = self.client.post(
            "/api/v1/interview/evaluation/consistency-test?iterations=4",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["is_consistent"])
        self.assertLess(data["score_variance"], 1.0)
        self.assertEqual(data["total_runs"], 4)

    def test_adaptive_interview_integration_with_rubric(self) -> None:
        """Test that submitting an answer in an interview session yields rich rubric evaluation."""
        start_payload = {
            "role": "GenAI Engineer",
            "experience_years": 3,
            "total_questions": 2,
        }
        start_res = self.client.post("/api/v1/interview/start", json=start_payload, headers=self.headers)
        self.assertEqual(start_res.status_code, 200)
        session_id = start_res.json()["session_id"]
        active_q = start_res.json()["active_question"]
        q_id = active_q["question_id"]

        # Submit candidate answer
        answer_payload = {
            "session_id": session_id,
            "question_id": q_id,
            "answer": (
                "In Python, generator functions use yield for lazy evaluation, keeping memory usage constant O(1) "
                "when streaming LLM tokens. Unlike list comprehensions which load all items at once, "
                "generators pause state and resume when requested, preventing OOM errors."
            ),
        }
        ans_res = self.client.post(f"/api/v1/interview/{session_id}/answer", json=answer_payload, headers=self.headers)
        self.assertEqual(ans_res.status_code, 200)

        ans_data = ans_res.json()
        self.assertIn("evaluation", ans_data)
        eval_data = ans_data["evaluation"]
        self.assertIn("rubric_evaluation", eval_data)
        self.assertIsNotNone(eval_data["rubric_evaluation"])
        self.assertIn("evidence", eval_data)
        self.assertIn("corrections", eval_data)
        self.assertIn("next_exercises", eval_data)
        self.assertIn("disclaimer", eval_data)


if __name__ == "__main__":
    unittest.main()
