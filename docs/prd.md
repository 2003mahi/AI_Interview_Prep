# Product Requirements Document (PRD)

## 1. Executive Summary & Problem Statement
* **Target Audience**: Final-year engineering students, MCA graduates, and fresh graduates (0–1 years experience) in India targeting entry-level AI Engineer and Generative AI (GenAI) Engineer roles.
* **Core Problem**: Indian candidates aggressively consume course material, tutorials, and YouTube playlists, but suffer from a "tutorial trap." They cannot reliably demonstrate hands-on, job-specific technical competence in interviews. When probed on production trade-offs (e.g., chunking strategies, vector index limits, latency vs. throughput, fine-tuning vs. RAG, hallucination mitigation, or evaluating LLM outputs), their answers remain purely theoretical or reciting surface-level buzzwords.
* **Core Hypothesis**: By replacing passive interview prep with an **evidence-based readiness loop** (**Diagnose → Teach → Practice → Verify → Track Improvement**), candidates will measurably increase their technical interview pass rate and be able to provide verifiable evidence of their skills.

---

## 2. Differentiator & Unique Value Proposition (UVP)

### 2.1 The Core Differentiator: The Evidence-Based Readiness Loop
Instead of generic mock interview bots that just give subjective feedback like "good job" or "speak with more confidence", our platform enforces an empirical 5-stage loop:

1. **Diagnose**: Run a targeted diagnostic across 6 core competency domains (Python for AI, Vector DBs/RAG, LLM Orchestration, Model Fine-Tuning & Quantization, Evaluation/Guardrails, System Design for AI). Identify precise misconception vectors (e.g., candidate confuses cosine similarity with Euclidean distance in normalized spaces, or does not know how to handle context window truncation).
2. **Teach**: Serve concise (3–5 min read/interactive), targeted micro-remediations tailored to the specific diagnostic failure points—not generic courses.
3. **Practice**: Interactive, scaffolded simulation where candidates solve realistic engineering scenarios (e.g., debugging a failing RAG pipeline with high retrieval latency or hallucination).
4. **Verify**: Strict, rubric-based evaluation where candidate answers and mini-implementations are verified against objective unit tests, edge-case probes, and rigorous multi-dimensional technical rubrics.
5. **Track Improvement**: A quantifiable "Readiness Index" showing verifiable skill progression over time with an auditable transcript of proven capabilities.

### 2.2 Unique Value Proposition
> **"Stop guessing if you're interview-ready. Diagnose your blind spots with rigorous technical probes, fix them with targeted mini-drills, and verify your competence with evidence-based scoring calibrated for entry-level AI & GenAI roles in India."**

---

## 3. Assumptions Requiring Student Validation

| # | Assumption | Risk Level | How to Validate in MVP | Success Criteria |
|---|------------|------------|------------------------|------------------|
| A1 | Indian freshers are willing to complete multi-step verification tasks rather than just casual MCQ quizzes. | High | Track funnel completion: Diagnostic Start → Micro-drill → Verification submission. | ≥ 60% completion rate for candidates who start a diagnostic. |
| A2 | Candidates prioritize specific technical feedback and rubrics over general conversational practice (e.g., accent, soft skills). | Medium | Offer side-by-side: technical rubric vs. generic summary; measure click-through on detailed technical recommendations. | ≥ 70% of users inspect detailed rubric line-items. |
| A3 | Candidates understand Indian-market hiring bars (services firms e.g. TCS/Infosys GenAI teams vs. high-growth tech startups e.g. Sarvam, Krutrim, SaaS startups). | Medium | Interview 25 target students with customized diagnostic sets. | ≥ 80% agree the questions reflect real hiring discussions. |
| A4 | AI-based rubric scoring is perceived as trustworthy and not arbitrary or hallucinated. | High | Measure dispute/appeal rate on feedback and survey perceived fairness. | < 10% dispute rate; perceived fairness rating ≥ 4.2 / 5.0. |

---

## 4. Competitor Analysis & What Is NOT Unique

### 4.1 Competitive Landscape
1. **Generic LeetCode / HackerRank**: Excellent for DSA and SQL, but virtually zero coverage of GenAI system architecture, RAG pipelines, prompt evaluation, or embedding models.
2. **Interviewing.io / Pramp**: Peer and human mock interviews; high cost (prohibitive for Indian students) or inconsistent peer quality; lacks structured GenAI technical curriculum.
3. **InterviewWarmup (Google) / Generic AI Mock Tools (InterviewBuddy, Final Round AI)**:
   * Focus heavily on soft skills, behavioral questions, and generic conversational answers.
   * Superficial grading: uses general sentiment or keyword detection without verifying technical accuracy or algorithmic soundness.
4. **YouTube / Udemy / Scaler / PrepBytes**: High-volume, one-way content consumption. Zero evidence-based verification of what the student can actually execute.

### 4.2 Explicitly Non-Unique Features
To maintain complete intellectual honesty, the following features are standard utilities and **not** differentiators:
* Text-based question-and-answer chat interface.
* Basic Multiple Choice Questions (MCQs) for quick syntax checks.
* User authentication and basic profile dashboards.
* Generic text generation for explanation summaries.

---

## 5. User Personas

### Persona 1: "The Campus Tier-2/3 Upskiller" (Rohan, 21, Final Year B.Tech CSE)
* **Background**: Tier-3 college in Pune. Has completed Andrew Ng's courses and built a basic LangChain PDF chatbot following a tutorial.
* **Pain Point**: Gets rejected in technical interview rounds for entry-level AI roles. When asked "How would you handle document chunks that split across table boundaries?", he freezes because his project just used `RecursiveCharacterTextSplitter()` defaults.
* **Goal**: Understand what real AI interviewers test and get tangible practice answering architectural and trade-off questions.
* **Key Motivation**: Securing an off-campus 8–18 LPA AI Engineer role.

### Persona 2: "The Junior Service-to-Product Switcher" (Priya, 23, 1 Year Experience)
* **Background**: Working at an IT services company on general Java backend; self-studying GenAI to transition to a high-growth startup.
* **Pain Point**: Unsure whether her knowledge of embeddings, fine-tuning (LoRA/QLoRA), and agentic workflows meets the production engineering bar.
* **Goal**: Benchmark herself against startup-level GenAI engineering expectations and eliminate weak areas quickly.

---

## 6. Core User Journeys

### Journey 1: Baseline Diagnostic & Gap Analysis
1. User logs in, selects role target ("GenAI Engineer - Entry Level") and target domain (e.g., "RAG Architecture & Embeddings").
2. System presents an adaptive 5-question diagnostic (scenario-based probes + code analysis).
3. Candidate answers via structured input (trade-off explanation, code snippet, or debugging choice).
4. System calculates a domain score and outputs a **Gap Analysis Report** highlighting specific misconceptions (e.g., "Failure to account for chunk overlap causing context loss").

### Journey 2: The Remediation & Practice Loop
1. User clicks **"Fix Gap"** on a diagnosed weakness.
2. System presents a 3-minute structured conceptual card with clear anti-patterns vs. best practices.
3. User completes a targeted drill (e.g., "Given this failing retrieval test case, adjust the chunking strategy and embedding metric").
4. Real-time feedback verifies immediate grasp of the concept.

### Journey 3: The Verification & Audit Trial
1. User enters **"Verification Challenge"** (simulated interview round).
2. AI interviewer probes candidate with follow-up constraints ("What if latency budget is 400ms and memory is constrained to 8GB?").
3. Verification engine grades the candidate across 4 rubric dimensions:
   - Technical Soundness
   - Trade-off Articulation
   - Edge-case Awareness
   - System Constraints Handling
4. System updates the candidate's **Evidence Log** and Readiness Score.

---

## 7. Scope Definition

### 7.1 In-Scope for MVP
* **Domain Focus**: 2 curated tracks:
  1. *AI Engineer (ML/Deep Learning Core)*: Data preprocessing, PyTorch fundamentals, model training lifecycle, metrics (Precision, Recall, ROC-AUC), deployment basics.
  2. *GenAI Engineer*: Embeddings & Vector Stores, RAG architectures, Prompt engineering & evaluation, LLM fine-tuning concepts (LoRA/PEFT), Guardrails & latency.
* **Diagnostic Engine**: 15 standardized scenario-based questions per track with rubrics.
* **Micro-Teaching Modules**: 15 targeted markdown/interactive remediation modules.
* **Practice Drills**: Scenario-based interactive exercises with structured prompt-based evaluation.
* **Verification Engine**: Single-turn and multi-turn technical interview simulation with strict LLM-as-a-judge rubric scoring.
* **Readiness Dashboard**: Visual domain breakdown, evidence log, and progress tracker over time.
* **Candidate History**: Session replay and rubric score history.

### 7.2 Out of Scope (Future Phases)
* Voice-to-voice real-time audio interaction (added in Phase 2 to prevent audio latency from ruining early technical testing).
* Live Python sandbox execution container with GPU (MVP uses static code analysis + test-case simulation).
* Enterprise recruiter portal for candidate sourcing.
* Comprehensive resume parser (MVP uses manual track selection).
* Automated LinkedIn badge generation.

---

## 8. Feature Acceptance Criteria (MVP)

| Feature ID | Feature Name | Detailed Acceptance Criteria |
|------------|--------------|------------------------------|
| **FEAT-01** | Track Selection & Onboarding | - User can choose between "AI Engineer" and "GenAI Engineer".<br>- Selection persists in profile and initializes topic graph. |
| **FEAT-02** | Diagnostic Assessment | - Generates exactly 5 questions per session matching candidate track.<br>- Mix of scenario analysis and architecture trade-offs.<br>- Must enforce time limit (optional toggle) and submission handling.<br>- Submitting triggers deterministic scoring against standardized rubrics. |
| **FEAT-03** | Gap Analysis Report | - Displays score (0–100%) broken into sub-domains.<br>- Explicitly identifies at least 1 "Primary Misconception" with evidence quote from candidate response.<br>- Provides direct link to relevant remediation module. |
| **FEAT-04** | Micro-Remediation (Teach) | - Displays concise (<500 words) lesson focusing on the identified misconception.<br>- Contains comparison table (Naive Approach vs. Production-Grade Approach). |
| **FEAT-05** | Practice Drill | - Presents 1 scenario exercise directly testing the remediated concept.<br>- Allows candidate 2 attempts with progressive hints.<br>- Verifies correctness via rubric before unlocking Verification mode. |
| **FEAT-06** | Verification Interview Round | - Simulates an interviewer providing a scenario + 1 adaptive follow-up based on candidate's initial answer.<br>- Evaluates using multi-criteria rubric (Soundness, Trade-offs, Edge cases).<br>- Generates specific, non-generic critique citing exact candidate sentences. |
| **FEAT-07** | Readiness Index & Evidence Log | - Computes weighted score per domain based only on completed verification tasks.<br>- Keeps historical timeline of attempts with score deltas.<br>- Allows exporting/viewing a summary evidence card. |

---

## 9. Measurable Success Metrics

### Product Performance Metrics
1. **Diagnostic-to-Remediation Transition**: ≥ 65% of candidates who take a diagnostic open the recommended micro-lesson within 24 hours.
2. **Loop Completion Rate**: ≥ 45% of users complete the full 5-step loop (Diagnose → Teach → Practice → Verify → Track) for at least one sub-domain.
3. **Verification Score Improvement**: Average score increase of ≥ 20 percentage points between diagnostic baseline and post-remediation verification on identical competency clusters.
4. **Evaluation Precision**: ≥ 85% agreement rate between AI rubric evaluations and human expert benchmarks on a sample of 50 test answers.
5. **System Latency**: P95 evaluation latency < 4.0 seconds for rubric grading.
