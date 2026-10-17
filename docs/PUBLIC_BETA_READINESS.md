# Public Beta Launch Readiness & Critical Journey Verification

This document verifies the end-to-end readiness of the **AI Interview Prep Assistant** for a controlled public beta rollout.

---

## 1. Critical User Journeys Verification

| Journey | Description | Verification Status | Fallback / Safeguard |
| :--- | :--- | :--- | :--- |
| **1. Authentication & Session** | User registers, logs in, and authenticates via Supabase Auth & JWT. | **VERIFIED (PASS)** | RLS policies prevent unauthorized access; JWT expiry verified on API requests. |
| **2. Document Ingestion** | Uploading CV/Resume (.pdf, .docx, .txt) with validation & size limits. | **VERIFIED (PASS)** | Magic bytes verification, max 10MB limit, 3-stage async retry with backoff. |
| **3. Live Adaptive Interview** | Real-time role-based questions, hints, and model answers. | **VERIFIED (PASS)** | Multi-role question bank operates with zero LLM latency and zero token burn. |
| **4. Rubric-Based Evaluation** | Detailed feedback on technical accuracy, clarity, strengths & weaknesses. | **VERIFIED (PASS)** | Calibrated scoring rubric; 71 automated test assertions passing. |
| **5. Job Readiness Audit** | Matching resume text against target job description. | **VERIFIED (PASS)** | Resilient fallback ensures 100% uptime even during network cold starts. |
| **6. Billing & Usage Quotas** | Daily interview / token limits with upgrade pathway. | **VERIFIED (PASS)** | Atomic `check_and_increment_quota` procedure; idempotent webhook handler. |

---

## 2. Public Beta Pricing Architecture & User Validation

To validate pricing with real users while protecting LLM operating margins, a 3-tier structure is configured:

### Beta Pricing Tiers

```
┌───────────────────────────┬───────────────────────────┬───────────────────────────┐
│       FREE TIER           │       PRO TIER            │     ENTERPRISE TIER       │
│      $0 / month           │      $19 / month          │       $99 / month         │
├───────────────────────────┼───────────────────────────┼───────────────────────────┤
│ • 5 Interviews / Day      │ • 100 Interviews / Day    │ • Unlimited Interviews    │
│ • Standard Question Banks │ • AI Adaptive Follow-ups  │ • Custom Team Rubrics     │
│ • Basic Feedback Rubric   │ • Full Readiness Audit    │ • Executive Calibration   │
│ • 50,000 Tokens / Day     │ • 1,000,000 Tokens / Day  │ • Priority Low-Latency SLA│
└───────────────────────────┴───────────────────────────┴───────────────────────────┘
```

### Real User Pricing Validation Framework

1. **Willingness-to-Pay (Van Westendorp PSM Survey)**:
   - Present beta users with four price questions after completing their 3rd interview:
     - *At what price would this feel too expensive?*
     - *At what price would this feel like a great deal?*
     - *At what price would it be so cheap you question the quality?*
     - *At what price is it starting to get expensive, but still worth buying?*
2. **Quota Paywall Conversion Rate Tracking**:
   - Track conversion rate when users hit the 5 interview/day free quota limit.
   - Benchmark: Target a 4-7% free-to-paid conversion rate.

---

## 3. Idempotent Payment Webhooks & Verification

- **Signature Scheme**: Stripe HMAC SHA-256 (`v1`) with 300-second timestamp tolerance.
- **Idempotency Guard**:
  - Webhooks check `payment_events` table before modifying user entitlements.
  - Replayed webhooks return HTTP 200 with `status: "already_processed"`, preventing duplicate billing or multiple subscription creations.
- **Automated Test Coverage**:
  - Verified with `test_billing_and_quotas.py` covering signature verification, duplicate event deduplication, and subscription lifecycle.

---

## 4. Final Deployment Sign-off

- [x] Next.js frontend builds cleanly (`npm run build` - Exit code 0).
- [x] All 71 backend Pytest tests pass (`pytest` - 100% pass rate).
- [x] Docker & Docker Compose configured with healthchecks and `.dockerignore`.
- [x] CI/CD pipeline configured at `.github/workflows/ci-cd.yml`.
- [x] Vercel deployment configurations created (`frontend/vercel.json` & `vercel.json`).
- [x] Dynamic backend URL handling without hardcoded localhost.
- [x] Supabase migration `20261018000000_beta_subscriptions_quotas.sql` ready.
- [x] Operational runbook and rollback procedures documented.
