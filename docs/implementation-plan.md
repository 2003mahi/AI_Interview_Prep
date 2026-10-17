# Phased Implementation Plan

## Phase 1: Foundations, Taxonomy & Seed Content
* **Objective**: Establish the relational schema, environment configurations, and initial high-quality question bank.
* **Tasks**:
  - [ ] **Task 1.1**: Initialize database schema (PostgreSQL) using Prisma/Drizzle with migrations as defined in [`data-model.md`](file:///c:/Users/DELL/Downloads/New%20folder/docs/data-model.md).
  - [ ] **Task 1.2**: Seed initial tracks (`genai_engineer`, `ai_engineer`) and 5 core competency domains.
  - [ ] **Task 1.3**: Author 15 diagnostic scenarios, 15 practice drills, and 15 verification interview prompts with complete rubric criteria and golden benchmarks.
  - [ ] **Task 1.4**: Author 15 concise (<500 words) micro-remediation lessons focusing on concrete production trade-offs.
* **Definition of Done (DoD)**: Database migrations run cleanly; seed data is verified via query; all question items have valid rubric guidelines.

---

## Phase 2: Diagnostic Engine & Gap Analysis
* **Objective**: Allow students to take an entry-level diagnostic and receive a deterministic, evidence-backed Gap Analysis Report.
* **Tasks**:
  - [ ] **Task 2.1**: Implement `POST /api/v1/diagnostics/sessions` (session initialization and question delivery).
  - [ ] **Task 2.2**: Implement LLM Judge scoring pipeline with Zod schema validation and retry fallback logic.
  - [ ] **Task 2.3**: Build evidence extraction routine to quote exact candidate phrases representing identified misconceptions.
  - [ ] **Task 2.4**: Implement `GET /api/v1/diagnostics/sessions/:id/report` returning visual domain scores and direct links to remediation.
* **Definition of Done (DoD)**: Candidate can complete a 5-question diagnostic; system generates a valid Gap Report within 4 seconds; LLM JSON parsing error rate is 0%.

---

## Phase 3: Remediation & Practice Drills (Teach → Practice)
* **Objective**: Close diagnosed skill gaps with bite-sized instruction and instant drill verification.
* **Tasks**:
  - [ ] **Task 3.1**: Implement `GET /api/v1/remediations/:domainId` delivering structured markdown with Anti-Pattern vs. Production-Pattern comparisons.
  - [ ] **Task 3.2**: Implement `POST /api/v1/drills/:questionId/attempt` with instant automated feedback and attempt limits (max 2 attempts).
  - [ ] **Task 3.3**: Unlock state transition from `PRACTICING` to `VERIFIED_READY` upon successful drill completion.
* **Definition of Done (DoD)**: User diagnosed with a gap can open the micro-lesson, complete the drill, receive instant rubric feedback, and unlock verification mode.

---

## Phase 4: Verification Simulation & Readiness Tracker (Verify → Track)
* **Objective**: Conduct rigorous multi-turn interview rounds and compile verifiable proof of competence.
* **Tasks**:
  - [ ] **Task 4.1**: Implement `POST /api/v1/verifications/sessions` and multi-turn turn submission `POST /api/v1/verifications/sessions/:id/turn` with dynamic interviewer follow-up constraints.
  - [ ] **Task 4.2**: Implement full 4-dimension rubric scoring (Technical Soundness, Trade-offs, Edge cases, Clarity).
  - [ ] **Task 4.3**: Implement `CandidateCompetency` updater and `EvidenceLog` writer to append verified quotes.
  - [ ] **Task 4.4**: Build the Readiness Dashboard UI displaying:
    - Current Verified Score vs. Baseline Score (showing % delta)
    - Verifiable Evidence Log (auditable list of demonstrated skills)
    - Target Bar Indicator (e.g. 75% for entry-level GenAI role).
* **Definition of Done (DoD)**: Multi-turn verification produces objective score, saves candidate evidence quote, and updates candidate readiness dashboard.

---

## Phase 5: Student Testing & Calibration
* **Objective**: Validate core assumptions with actual target users (final-year Indian engineering students & freshers).
* **Tasks**:
  - [ ] **Task 5.1**: Run 50 golden benchmark responses through the LLM Judge to verify Pearson correlation $r \ge 0.85$ against Senior Engineer scores.
  - [ ] **Task 5.2**: Conduct closed alpha test with 25 target students across Tier-2/3 and Tier-1 colleges.
  - [ ] **Task 5.3**: Measure loop completion funnel (Diagnose → Teach → Practice → Verify).
  - [ ] **Task 5.4**: Collect feedback on perceived fairness, question relevance to Indian interviews, and dispute rates.
* **Definition of Done (DoD)**: 25 completed student sessions; calibration benchmark verified; dispute rate < 10%; assumption validation scorecard documented.
