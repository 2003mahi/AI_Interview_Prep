"""Unit & Integration Tests for Job Readiness Analyzer.

Validates:
1. Skill extraction accuracy and symbol handling (C++, C#, Node.js, Next.js, CI/CD).
2. Distinction between missing resume evidence and genuine missing knowledge.
3. Prerequisite resolution and targeted exercise generation.
4. Edge cases (empty strings, whitespace, 100% match, 0% match, deduplication).
5. Supabase persistence repository operations.
6. REST API routes with authentication and cross-user security isolation.
"""

import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.main import app
from app.schemas.readiness import (
    GapType,
    JobReadinessAnalysisResult,
    PriorityLevel,
)
from app.services.document_repository import document_repository
from app.services.job_readiness_analyzer import job_readiness_analyzer
from app.services.readiness_repository import job_readiness_repository


class TestSkillExtractionAccuracy(unittest.TestCase):
    """Test accuracy of skill extraction from varied real-world texts."""

    def test_canonical_skills_and_symbols(self):
        text = (
            "Looking for an experienced engineer proficient in C++, C#, Python, "
            "and Node.js. Experience with Next.js, Docker, Kubernetes, and CI/CD pipelines is required."
        )
        skills = job_readiness_analyzer.extract_skills(text)
        self.assertIn("c++", skills)
        self.assertIn("c#", skills)
        self.assertIn("python", skills)
        self.assertIn("node.js", skills)
        self.assertIn("next.js", skills)
        self.assertIn("docker", skills)
        self.assertIn("kubernetes", skills)
        self.assertIn("ci/cd", skills)

    def test_case_insensitivity_and_delimiters(self):
        text = "FASTAPI; PostgreSQL • REDIS\n- Terraform\n* System Design"
        skills = job_readiness_analyzer.extract_skills(text)
        self.assertIn("fastapi", skills)
        self.assertIn("postgresql", skills)
        self.assertIn("redis", skills)
        self.assertIn("terraform", skills)
        self.assertIn("system design", skills)

    def test_deduplication(self):
        text = "Python, python, PYTHON, Python programming, Python"
        skills = job_readiness_analyzer.extract_skills(text)
        self.assertIn("python", skills)
        # Should contain lowercase canonical python
        self.assertEqual(len([s for s in skills if s == "python"]), 1)


class TestDistinguishMissingEvidenceFromMissingKnowledge(unittest.TestCase):
    """Core requirement: Distinguish missing resume evidence from genuine knowledge gaps."""

    def test_evidence_vs_resume_gap_vs_knowledge_gap(self):
        # JD requires 3 skills:
        # 1. Python (in resume -> evidence)
        # 2. Docker (NOT in resume, BUT in learning notes -> missing resume evidence)
        # 3. Kubernetes (NOT in resume, NOT in notes/demo -> missing knowledge)
        jd_text = "Requirements: Python, Docker, Kubernetes"
        resume_text = "Experienced in Python development and building REST services."
        notes_text = "Studied Docker containerization, multi-stage builds, and volumes."
        demo_text = ""

        result = job_readiness_analyzer.analyze(
            resume_text=resume_text,
            job_description_text=jd_text,
            learning_notes_text=notes_text,
            demonstrated_skills_text=demo_text,
            job_title="Backend Engineer",
        )

        # 1. Python should be in evidence
        evidence_skills = [e.skill for e in result.evidence]
        self.assertIn("python", evidence_skills)

        # 2. Docker should be in missing_resume_evidence (candidate knows it, but omitted from resume)
        missing_resume_skills = [g.skill for g in result.missing_resume_evidence]
        self.assertIn("docker", missing_resume_skills)
        docker_gap = next(g for g in result.missing_resume_evidence if g.skill == "docker")
        self.assertEqual(docker_gap.gap_type, GapType.MISSING_RESUME_EVIDENCE)
        self.assertIn("resume", docker_gap.actionable_recommendation.lower())

        # 3. Kubernetes should be in missing_knowledge (genuine gap)
        missing_knowledge_skills = [g.skill for g in result.missing_knowledge]
        self.assertIn("kubernetes", missing_knowledge_skills)
        k8s_gap = next(g for g in result.missing_knowledge if g.skill == "kubernetes")
        self.assertEqual(k8s_gap.gap_type, GapType.MISSING_KNOWLEDGE)
        self.assertIsNotNone(k8s_gap.targeted_exercise)
        self.assertIn("Kubernetes", k8s_gap.targeted_exercise.title)

    def test_demonstrated_skill_flags_missing_resume_evidence(self):
        jd_text = "Required skills: FastAPI, Redis"
        resume_text = "Software Engineer with 3 years building web apps."
        demo_text = "Demonstrated interview score: 95/100 on FastAPI endpoint implementation and rate limiting with Redis."

        result = job_readiness_analyzer.analyze(
            resume_text=resume_text,
            job_description_text=jd_text,
            demonstrated_skills_text=demo_text,
        )

        missing_resume_skills = [g.skill for g in result.missing_resume_evidence]
        self.assertIn("fastapi", missing_resume_skills)
        self.assertIn("redis", missing_resume_skills)
        # Since candidate demonstrated both, missing knowledge must be empty
        self.assertEqual(len(result.missing_knowledge), 0)


class TestPrerequisitesAndTargetedExercises(unittest.TestCase):
    """Test prerequisite resolution and targeted exercise composition."""

    def test_prerequisites_mapping(self):
        jd_text = "Requirements: React, Kubernetes, FastAPI"
        result = job_readiness_analyzer.analyze(job_description_text=jd_text)

        self.assertIn("react", result.prerequisites_map)
        self.assertIn("javascript", result.prerequisites_map["react"])
        self.assertIn("kubernetes", result.prerequisites_map)
        self.assertIn("docker", result.prerequisites_map["kubernetes"])
        self.assertIn("fastapi", result.prerequisites_map)
        self.assertIn("python", result.prerequisites_map["fastapi"])

    def test_targeted_exercises_generation(self):
        jd_text = "Requirements: FastAPI, Docker"
        result = job_readiness_analyzer.analyze(job_description_text=jd_text)

        self.assertTrue(len(result.targeted_exercises) >= 2)
        exercise_skills = [ex.skill for ex in result.targeted_exercises]
        self.assertIn("fastapi", exercise_skills)
        self.assertIn("docker", exercise_skills)

        fastapi_ex = next(ex for ex in result.targeted_exercises if ex.skill == "fastapi")
        self.assertTrue(len(fastapi_ex.acceptance_criteria) > 0)
        self.assertTrue(fastapi_ex.estimated_time_minutes > 0)


class TestEdgeCases(unittest.TestCase):
    """Edge cases: empty inputs, zero match, 100% match, whitespace, noise."""

    def test_empty_and_whitespace_inputs(self):
        result = job_readiness_analyzer.analyze(
            resume_text="   \n  \t  ",
            job_description_text="",
            learning_notes_text=None,
            demonstrated_skills_text=None,
        )
        self.assertEqual(result.required_skills, [])
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.missing_resume_evidence, [])
        self.assertEqual(result.missing_knowledge, [])
        self.assertEqual(result.readiness_score.overall_score, 0.0)

    def test_100_percent_readiness(self):
        jd_text = "Requirements: Python, SQL, Docker"
        resume_text = "Expert in Python, SQL databases, and Docker container deployment."
        demos_text = "Passed Python, SQL, and Docker coding benchmarks."

        result = job_readiness_analyzer.analyze(
            resume_text=resume_text,
            job_description_text=jd_text,
            demonstrated_skills_text=demos_text,
        )
        self.assertEqual(len(result.evidence), 3)
        self.assertEqual(len(result.missing_resume_evidence), 0)
        self.assertEqual(len(result.missing_knowledge), 0)
        self.assertEqual(result.readiness_score.resume_coverage_score, 100.0)
        self.assertEqual(result.readiness_score.overall_score, 100.0)

    def test_zero_percent_readiness(self):
        jd_text = "Requirements: Rust, Kubernetes, Terraform"
        resume_text = "Experience in Marketing, SEO, and copywriting."

        result = job_readiness_analyzer.analyze(
            resume_text=resume_text,
            job_description_text=jd_text,
        )
        self.assertEqual(len(result.evidence), 0)
        self.assertEqual(len(result.missing_resume_evidence), 0)
        self.assertEqual(len(result.missing_knowledge), 3)
        self.assertEqual(result.readiness_score.overall_score, 0.0)


class TestSupabasePersistenceAndRepository(unittest.IsolatedAsyncioTestCase):
    """Test persisting, querying, and deleting analyses via repository."""

    async def test_save_and_retrieve_analysis(self):
        analysis = job_readiness_analyzer.analyze(
            resume_text="Python, Docker",
            job_description_text="Python, Docker, Kubernetes",
            learning_notes_text="Kubernetes cluster basics",
        )
        user_id = "test-user-persistence-uuid"
        record = await job_readiness_repository.save_analysis(
            user_id=user_id,
            analysis=analysis,
            job_title="DevOps Engineer",
        )

        self.assertIsNotNone(record.id)
        self.assertEqual(record.user_id, user_id)
        self.assertEqual(record.job_title, "DevOps Engineer")
        self.assertGreater(record.overall_score, 0.0)

        # Retrieve by ID
        fetched = await job_readiness_repository.get_by_id(record.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, record.id)
        self.assertEqual(len(fetched.analysis.required_skills), 3)

        # List for user
        user_list = await job_readiness_repository.list_for_user(user_id=user_id)
        self.assertTrue(any(r.id == record.id for r in user_list))

        # Delete
        deleted = await job_readiness_repository.delete(record.id)
        self.assertTrue(deleted)
        self.assertIsNone(await job_readiness_repository.get_by_id(record.id))


class TestReadinessApiEndpoints(unittest.TestCase):
    """Test FastAPI REST endpoints, auth verification, and cross-user isolation."""

    def setUp(self):
        self.client = TestClient(app)
        self.user1_id = "user-1111-readiness"
        self.user2_id = "user-2222-readiness"
        self.token_user1 = create_access_token(user_id=self.user1_id, email="user1@example.com")
        self.token_user2 = create_access_token(user_id=self.user2_id, email="user2@example.com")
        self.headers_user1 = {"Authorization": f"Bearer {self.token_user1}"}
        self.headers_user2 = {"Authorization": f"Bearer {self.token_user2}"}

    def test_analyze_endpoint_success(self):
        payload = {
            "job_title": "Full Stack Engineer",
            "job_description_text": "Required skills: React, TypeScript, FastAPI, PostgreSQL",
            "resume_text": "Experienced building frontends in React and TypeScript.",
            "learning_notes_text": "Studied FastAPI async routing and dependencies.",
            "demonstrated_skills_text": "Completed PostgreSQL optimization lab.",
        }
        res = self.client.post("/api/v1/readiness/analyze", json=payload, headers=self.headers_user1)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("id", data)
        self.assertEqual(data["user_id"], self.user1_id)
        self.assertEqual(data["job_title"], "Full Stack Engineer")

        analysis = data["analysis"]
        self.assertIn("react", analysis["required_skills"])
        self.assertIn("typescript", analysis["required_skills"])
        self.assertIn("fastapi", analysis["required_skills"])
        self.assertIn("postgresql", analysis["required_skills"])

        # Check evidence & gaps
        evidence_skills = [e["skill"] for e in analysis["evidence"]]
        self.assertIn("react", evidence_skills)
        self.assertIn("typescript", evidence_skills)

        # FastAPI & PostgreSQL were NOT in resume but in notes/demos -> missing_resume_evidence
        missing_resume = [g["skill"] for g in analysis["missing_resume_evidence"]]
        self.assertIn("fastapi", missing_resume)
        self.assertIn("postgresql", missing_resume)

    def test_analyze_endpoint_missing_jd_fails(self):
        payload = {
            "resume_text": "Python engineer",
            "job_description_text": "",
        }
        res = self.client.post("/api/v1/readiness/analyze", json=payload, headers=self.headers_user1)
        self.assertEqual(res.status_code, 400)

    def test_cross_user_isolation(self):
        # User 1 creates an analysis
        payload = {
            "job_title": "Security Analyst",
            "job_description_text": "Requirements: Python, Linux",
            "resume_text": "Python developer",
        }
        create_res = self.client.post("/api/v1/readiness/analyze", json=payload, headers=self.headers_user1)
        self.assertEqual(create_res.status_code, 200)
        analysis_id = create_res.json()["id"]

        # User 1 can view it
        get_res1 = self.client.get(f"/api/v1/readiness/analyses/{analysis_id}", headers=self.headers_user1)
        self.assertEqual(get_res1.status_code, 200)

        # User 2 CANNOT view it -> 404
        get_res2 = self.client.get(f"/api/v1/readiness/analyses/{analysis_id}", headers=self.headers_user2)
        self.assertEqual(get_res2.status_code, 404)

        # User 2 CANNOT delete it -> 404
        del_res2 = self.client.delete(f"/api/v1/readiness/analyses/{analysis_id}", headers=self.headers_user2)
        self.assertEqual(del_res2.status_code, 404)

        # User 1 CAN delete it -> 204
        del_res1 = self.client.delete(f"/api/v1/readiness/analyses/{analysis_id}", headers=self.headers_user1)
        self.assertEqual(del_res1.status_code, 204)


if __name__ == "__main__":
    unittest.main()
