"""Job Readiness Analyzer Engine.

Compares resumes, job descriptions, learning notes, and demonstrated skills.
Distinguishes missing resume evidence from genuine knowledge gaps.
Produces validated JSON with required skills, evidence, gaps, priorities,
prerequisites, targeted exercises, and readiness scores.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..schemas.readiness import (
    GapItem,
    GapType,
    JobReadinessAnalysisResult,
    PriorityGroup,
    PriorityLevel,
    ReadinessScoreBreakdown,
    SkillEvidence,
    TargetedExercise,
)

# Canonical knowledge base of common technical skills, frameworks, tools, and concepts
CANONICAL_SKILLS = [
    # Languages
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang", "rust", "ruby", "php", "sql", "html", "css",
    # Frameworks & Libraries
    "react", "next.js", "vue", "angular", "node.js", "express", "fastapi", "django", "flask", "spring boot", "asp.net",
    # Cloud & DevOps
    "docker", "kubernetes", "aws", "gcp", "azure", "terraform", "ci/cd", "github actions", "linux", "git",
    # Databases & Storage
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "dynamodb", "supabase",
    # Architecture & Concepts
    "rest apis", "graphql", "microservices", "system design", "distributed systems", "tdd", "unit testing", "agile",
    "data structures", "algorithms", "performance optimization", "concurrency", "asyncio",
]

# Prerequisite mapping for common technologies
PREREQUISITE_MAP: Dict[str, List[str]] = {
    "react": ["javascript", "html", "css"],
    "next.js": ["react", "javascript", "typescript"],
    "typescript": ["javascript"],
    "fastapi": ["python", "rest apis"],
    "django": ["python", "sql"],
    "kubernetes": ["docker", "linux"],
    "docker": ["linux"],
    "terraform": ["cloud (aws/gcp/azure)", "devops"],
    "microservices": ["system design", "rest apis", "docker"],
    "system design": ["distributed systems", "sql", "data structures"],
    "ci/cd": ["git", "docker"],
    "graphql": ["rest apis", "javascript/python"],
    "asyncio": ["python", "concurrency"],
}

# Exercise templates for targeted practice
EXERCISE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "fastapi": {
        "title": "Build a Resilient REST API with FastAPI and Pydantic",
        "description": "Develop a CRUD microservice using FastAPI, dependency injection, and Pydantic v2 schemas.",
        "prerequisites": ["python", "rest apis"],
        "estimated_time_minutes": 60,
        "acceptance_criteria": [
            "Implement input validation and error handlers.",
            "Write at least 3 pytest integration tests using TestClient.",
            "Include JWT bearer token authentication middleware."
        ]
    },
    "docker": {
        "title": "Multi-Stage Production Containerization",
        "description": "Write a clean, multi-stage Dockerfile minimizing image footprint and securing container user permissions.",
        "prerequisites": ["linux"],
        "estimated_time_minutes": 45,
        "acceptance_criteria": [
            "Use non-root user execution in production stage.",
            "Create docker-compose.yml with healthcheck configured.",
            "Ensure final image size is under 200MB."
        ]
    },
    "kubernetes": {
        "title": "Deploy Scalable Service with Kubernetes Manifests",
        "description": "Create Deployment, Service, and HPA (Horizontal Pod Autoscaler) resource manifests.",
        "prerequisites": ["docker", "linux"],
        "estimated_time_minutes": 75,
        "acceptance_criteria": [
            "Configure liveness and readiness probes.",
            "Define CPU/Memory resource requests and limits.",
            "Test deployment rollout and rollback behavior."
        ]
    },
    "react": {
        "title": "Build an Accessible, Interactive Dashboard Component",
        "description": "Construct a responsive component with state management, debounce search, and error boundary.",
        "prerequisites": ["javascript", "html", "css"],
        "estimated_time_minutes": 60,
        "acceptance_criteria": [
            "Handle loading, empty, and error states gracefully.",
            "Implement memoization using useMemo/useCallback to avoid redundant renders.",
            "Pass WCAG keyboard navigation accessibility tests."
        ]
    },
    "system design": {
        "title": "Design a Distributed Rate Limiter and Caching Architecture",
        "description": "Formulate a scalable system design document detailing token bucket algorithms, Redis caching, and database failover.",
        "prerequisites": ["distributed systems", "sql"],
        "estimated_time_minutes": 90,
        "acceptance_criteria": [
            "Calculate throughput, bandwidth, and storage QPS requirements.",
            "Address cache invalidation and stampede mitigation.",
            "Diagram end-to-end component data flow."
        ]
    },
}


class JobReadinessAnalyzer:
    """Core domain service for job readiness extraction and comparison."""

    def _normalize(self, text: str) -> str:
        """Standardize text for comparison."""
        return text.lower().strip()

    def _extract_snippets(self, text: str, skill: str, window: int = 120) -> List[str]:
        """Find matching context snippets for a skill within text."""
        if not text or not skill:
            return []

        pattern = rf"(?<![a-zA-Z0-9#+])({re.escape(skill)})(?![a-zA-Z0-9#+])"
        snippets: List[str] = []
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = max(0, match.start() - window // 2)
            end = min(len(text), match.end() + window // 2)
            snippet = text[start:end].replace("\n", " ").strip()
            if snippet and snippet not in snippets:
                snippets.append(f"...{snippet}...")
            if len(snippets) >= 2:
                break
        return snippets

    def extract_skills(self, text: Optional[str]) -> Set[str]:
        """Extract recognized and candidate technical skills from text with accuracy and deduplication."""
        if not text or not text.strip():
            return set()

        text_norm = self._normalize(text)
        found_skills: Set[str] = set()

        # 1. Match against canonical dictionary with boundary awareness (handles punctuation like trailing dots/commas)
        for skill in CANONICAL_SKILLS:
            pattern = rf"(?<![a-zA-Z0-9#+])({re.escape(skill)})(?![a-zA-Z0-9#+])"
            if re.search(pattern, text_norm):
                found_skills.add(skill)


        # 2. Extract bulleted list items or comma/newline delimited skill sections
        delimiters = [",", ";", "\n", "•", "-", "*", "|"]
        cleaned_text = text
        for d in delimiters:
            cleaned_text = cleaned_text.replace(d, "\n")

        for line in cleaned_text.split("\n"):
            candidate = self._normalize(line)
            # Remove prefixes like 'proficient in:', 'experience with:', 'skills:'
            candidate = re.sub(r"^(skills|requirements|proficient in|experience with|tools|knowledge of):\s*", "", candidate)
            candidate = candidate.strip()
            # If candidate is short, reasonable length (2 to 30 chars), and looks like a valid skill name
            if 2 <= len(candidate) <= 30 and re.match(r"^[a-z0-9#\+\.\-\s/]+$", candidate):
                # Filter out obvious conversational noise words
                stop_words = {"and", "with", "or", "in", "the", "for", "years", "experience", "required", "preferred"}
                if candidate not in stop_words and not candidate.isnumeric():
                    found_skills.add(candidate)

        return found_skills

    def _determine_priority(self, skill: str, jd_text: str) -> PriorityLevel:
        """Determine whether a skill is High, Medium, or Low priority."""
        skill_norm = skill.lower()
        jd_norm = jd_text.lower() if jd_text else ""

        # Check if mentioned near 'must have', 'required', 'core', or 'essential'
        strong_requirement_pattern = rf"(must have|required|core|essential|minimum)[\s\w\W]{{0,60}}\b{re.escape(skill_norm)}\b"
        if re.search(strong_requirement_pattern, jd_norm) or skill_norm in ["system design", "python", "javascript", "sql"]:
            return PriorityLevel.HIGH

        # Check if mentioned near 'nice to have', 'bonus', 'plus', 'optional'
        optional_pattern = rf"(nice to have|plus|bonus|optional|preferred)[\s\w\W]{{0,60}}\b{re.escape(skill_norm)}\b"
        if re.search(optional_pattern, jd_norm):
            return PriorityLevel.LOW

        return PriorityLevel.MEDIUM

    def _build_exercise_for_skill(self, skill: str, prerequisites: List[str]) -> TargetedExercise:
        """Build or adapt a targeted hands-on exercise for a skill."""
        skill_key = skill.lower()
        if skill_key in EXERCISE_TEMPLATES:
            tpl = EXERCISE_TEMPLATES[skill_key]
            return TargetedExercise(
                skill=skill,
                title=tpl["title"],
                description=tpl["description"],
                prerequisites=tpl.get("prerequisites", prerequisites),
                estimated_time_minutes=tpl.get("estimated_time_minutes", 60),
                acceptance_criteria=tpl.get("acceptance_criteria", []),
            )

        # Dynamic fallback exercise
        return TargetedExercise(
            skill=skill,
            title=f"Hands-on {skill.title()} Implementation & Validation",
            description=f"Create a practical proof-of-concept project demonstrating proficiency in {skill}.",
            prerequisites=prerequisites,
            estimated_time_minutes=45,
            acceptance_criteria=[
                f"Implement a working solution solving a standard real-world {skill} challenge.",
                "Include unit tests and automated verification scripts.",
                "Document technical decisions and trade-offs in README."
            ],
        )

    def analyze(
        self,
        resume_text: Optional[str] = None,
        job_description_text: Optional[str] = None,
        learning_notes_text: Optional[str] = None,
        demonstrated_skills_text: Optional[str] = None,
        job_title: Optional[str] = "Software Engineer",
    ) -> JobReadinessAnalysisResult:
        """Compare all sources and distinguish missing resume evidence from missing knowledge."""
        resume_raw = resume_text or ""
        jd_raw = job_description_text or ""
        notes_raw = learning_notes_text or ""
        demos_raw = demonstrated_skills_text or ""

        # Extract skills from each source
        jd_skills = self.extract_skills(jd_raw)
        resume_skills = self.extract_skills(resume_raw)
        notes_skills = self.extract_skills(notes_raw)
        demos_skills = self.extract_skills(demos_raw)

        # Combined non-resume candidate skills (what candidate knows/demonstrated)
        demonstrated_or_noted = notes_skills | demos_skills

        required_skills_list = sorted(list(jd_skills))
        evidence_list: List[SkillEvidence] = []
        missing_resume_evidence: List[GapItem] = []
        missing_knowledge: List[GapItem] = []

        priorities = PriorityGroup(high=[], medium=[], low=[])
        prerequisites_map: Dict[str, List[str]] = {}
        all_exercises: List[TargetedExercise] = []

        # If no skills detected in JD (e.g. empty JD string), handle gracefully
        if not required_skills_list:
            readiness_breakdown = ReadinessScoreBreakdown(
                overall_score=0.0,
                resume_coverage_score=0.0,
                demonstrated_skill_score=0.0,
                knowledge_coverage_score=0.0,
                summary="No required skills found in job description. Please provide a detailed job description."
            )
            return JobReadinessAnalysisResult(
                job_title=job_title,
                required_skills=[],
                evidence=[],
                missing_resume_evidence=[],
                missing_knowledge=[],
                priorities=priorities,
                prerequisites_map={},
                targeted_exercises=[],
                readiness_score=readiness_breakdown,
            )

        for skill in required_skills_list:
            in_resume = skill in resume_skills
            in_notes = skill in notes_skills
            in_demos = skill in demos_skills

            # Extract evidence snippets across available text sources
            sources: List[str] = []
            snippets: List[str] = []

            if in_resume:
                sources.append("resume")
                snippets.extend(self._extract_snippets(resume_raw, skill))
            if in_demos:
                sources.append("demonstrated")
                snippets.extend(self._extract_snippets(demos_raw, skill))
            if in_notes:
                sources.append("notes")
                snippets.extend(self._extract_snippets(notes_raw, skill))

            # Determine prerequisites
            prereqs = PREREQUISITE_MAP.get(skill.lower(), [])
            if prereqs:
                prerequisites_map[skill] = prereqs

            # Categorize Priority
            priority = self._determine_priority(skill, jd_raw)

            # SCENARIO 1: Resume Evidence Exists
            if in_resume:
                proficiency = "demonstrated" if in_demos else ("noted" if in_notes else "claimed_on_resume")
                evidence_list.append(
                    SkillEvidence(
                        skill=skill,
                        sources=sources,
                        evidence_snippets=snippets,
                        proficiency_level=proficiency,
                    )
                )

            # SCENARIO 2: NOT in Resume, but candidate demonstrated or noted it -> MISSING RESUME EVIDENCE
            elif in_demos or in_notes:
                source_label = "demonstrated code / practice sessions" if in_demos else "learning notes"
                rec = (
                    f"You have demonstrated proficiency in '{skill}' within your {source_label}, "
                    f"but it is completely omitted from your resume. "
                    f"Action: Add a dedicated bullet point under your experience or project sections highlighting your work with {skill}."
                )
                gap_item = GapItem(
                    skill=skill,
                    gap_type=GapType.MISSING_RESUME_EVIDENCE,
                    priority=priority,
                    reason=f"Demonstrated in candidate {source_label}, but missing verifiable resume evidence.",
                    actionable_recommendation=rec,
                    prerequisites=prereqs,
                    targeted_exercise=None,  # Candidate already knows this, just needs resume update!
                )
                missing_resume_evidence.append(gap_item)

                # Add to priorities
                if priority == PriorityLevel.HIGH:
                    priorities.high.append(skill)
                elif priority == PriorityLevel.MEDIUM:
                    priorities.medium.append(skill)
                else:
                    priorities.low.append(skill)

            # SCENARIO 3: NOT in Resume AND NOT demonstrated/noted -> MISSING KNOWLEDGE
            else:
                exercise = self._build_exercise_for_skill(skill, prereqs)
                all_exercises.append(exercise)

                rec = (
                    f"Genuine skill gap: '{skill}' is required for this role but not found in your resume, notes, or demonstrated skills. "
                    f"Action: Complete the targeted hands-on exercise '{exercise.title}' to build foundational competency."
                )
                gap_item = GapItem(
                    skill=skill,
                    gap_type=GapType.MISSING_KNOWLEDGE,
                    priority=priority,
                    reason="Required skill absent across all candidate artifacts (resume, notes, and demonstration logs).",
                    actionable_recommendation=rec,
                    prerequisites=prereqs,
                    targeted_exercise=exercise,
                )
                missing_knowledge.append(gap_item)

                # Add to priorities
                if priority == PriorityLevel.HIGH:
                    priorities.high.append(skill)
                elif priority == PriorityLevel.MEDIUM:
                    priorities.medium.append(skill)
                else:
                    priorities.low.append(skill)

        # Calculate scores
        total_required = len(required_skills_list)
        resume_matches = len(evidence_list)
        missing_evidence_count = len(missing_resume_evidence)
        missing_knowledge_count = len(missing_knowledge)

        # Coverage scores
        resume_coverage = round((resume_matches / total_required) * 100.0, 1)
        demonstrated_coverage = round(
            (len([e for e in evidence_list if "demonstrated" in e.sources] +
             [g for g in missing_resume_evidence if g.skill in demos_skills]) / total_required) * 100.0,
            1
        )
        knowledge_coverage = round(((total_required - missing_knowledge_count) / total_required) * 100.0, 1)

        # Overall weighted readiness score:
        # 50% knowledge present + 30% resume documented + 20% demonstrated verification
        overall_score = round(
            (knowledge_coverage * 0.50) + (resume_coverage * 0.30) + (demonstrated_coverage * 0.20),
            1
        )

        summary = (
            f"Candidate meets {knowledge_coverage}% of core knowledge requirements. "
            f"Resume covers {resume_coverage}% of required skills. "
            f"{missing_evidence_count} demonstrated skill(s) need to be added to resume. "
            f"{missing_knowledge_count} skill(s) represent genuine knowledge gaps."
        )

        breakdown = ReadinessScoreBreakdown(
            overall_score=overall_score,
            resume_coverage_score=resume_coverage,
            demonstrated_skill_score=demonstrated_coverage,
            knowledge_coverage_score=knowledge_coverage,
            summary=summary,
        )

        return JobReadinessAnalysisResult(
            job_title=job_title,
            required_skills=required_skills_list,
            evidence=evidence_list,
            missing_resume_evidence=missing_resume_evidence,
            missing_knowledge=missing_knowledge,
            priorities=priorities,
            prerequisites_map=prerequisites_map,
            targeted_exercises=all_exercises,
            readiness_score=breakdown,
        )


job_readiness_analyzer = JobReadinessAnalyzer()
