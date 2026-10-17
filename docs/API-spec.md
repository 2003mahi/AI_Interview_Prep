# REST API Specification (OpenAPI-Compliant)

## 1. Global Conventions
* **Base URL**: `/api/v1`
* **Content-Type**: `application/json`
* **Authentication**: Bearer JWT token in header (`Authorization: Bearer <token>`).
* **Standard Error Response Format**:
```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "Human-readable explanation",
    "details": []
  }
}
```

---

## 2. Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/tracks` | List available career tracks & competency domains |
| `POST` | `/api/v1/diagnostics/sessions` | Initialize a new diagnostic assessment session |
| `POST` | `/api/v1/diagnostics/sessions/:id/submit` | Submit answers for a diagnostic session |
| `GET` | `/api/v1/diagnostics/sessions/:id/report` | Fetch diagnostic gap analysis report |
| `GET` | `/api/v1/remediations/:domainId` | Fetch targeted micro-lesson for a weak domain |
| `POST` | `/api/v1/drills/:questionId/attempt` | Submit candidate answer for a practice drill |
| `POST` | `/api/v1/verifications/sessions` | Start a simulated verification interview session |
| `POST` | `/api/v1/verifications/sessions/:id/turn` | Submit candidate response to an interview question / probe |
| `GET` | `/api/v1/readiness/profile` | Get candidate's current Readiness Index & domain scores |
| `GET` | `/api/v1/readiness/evidence` | Fetch verifiable evidence log and historical quotes |

---

## 3. Detailed Endpoint Contracts

### 3.1 Start Diagnostic Session
* **Endpoint**: `POST /api/v1/diagnostics/sessions`
* **Request Body**:
```json
{
  "trackSlug": "genai_engineer"
}
```
* **Response `201 Created`**:
```json
{
  "sessionId": "4a73b221-12c8-47e1-b4f0-8ff90d981881",
  "track": "genai_engineer",
  "totalQuestions": 5,
  "questions": [
    {
      "questionId": "e1f18820-b80c-45a8-92a1-fa366bf9b932",
      "domainSlug": "vector_dbs_and_embeddings",
      "domainTitle": "Vector Databases & Embeddings",
      "prompt": "You are building a customer support Q&A bot over dense PDF manuals containing complex technical tables. Your naive RAG pipeline with 500-token chunks is returning irrelevant text when users ask for specific tabular values. What are two specific failure modes of your chunking strategy, and how would you redesign the ingestion pipeline?",
      "codeSnippet": null,
      "timeLimitSeconds": 300
    }
  ]
}
```

---

### 3.2 Submit Diagnostic & Generate Gap Analysis
* **Endpoint**: `POST /api/v1/diagnostics/sessions/:id/submit`
* **Request Body**:
```json
{
  "answers": [
    {
      "questionId": "e1f18820-b80c-45a8-92a1-fa366bf9b932",
      "candidateAnswer": "I would just increase chunk size to 2000 tokens so the whole table fits in one chunk. Then use any standard cosine similarity."
    }
  ]
}
```
* **Response `200 OK`**:
```json
{
  "sessionId": "4a73b221-12c8-47e1-b4f0-8ff90d981881",
  "overallScore": 42.5,
  "status": "completed",
  "domains": [
    {
      "domainSlug": "vector_dbs_and_embeddings",
      "score": 35.0,
      "status": "critical_gap",
      "misconceptionIdentified": "Assumes increasing chunk size solves table parsing without semantic structure awareness; ignores noise dilution and token overflow.",
      "candidateEvidenceQuote": "\"just increase chunk size to 2000 tokens\"",
      "recommendedRemediationId": "c49a37bd-901d-44a6-98dc-a7bc8100192e"
    }
  ]
}
```

---

### 3.3 Get Targeted Remediation (Micro-Lesson)
* **Endpoint**: `GET /api/v1/remediations/:domainId`
* **Response `200 OK`**:
```json
{
  "domainId": "c49a37bd-901d-44a6-98dc-a7bc8100192e",
  "domainTitle": "Vector Databases & Embeddings",
  "estimatedReadMinutes": 3,
  "contentMarkdown": "# Handling Tabular & Semi-Structured Data in RAG\n\n### The Naive Trap\nIncreasing chunk size to 2000 tokens dilutes embedding density...",
  "antiPatterns": [
    "Treating Markdown / HTML tables as pure raw text",
    "Blindly increasing chunk size without evaluating embedding vector dilution"
  ],
  "productionPatterns": [
    "Extracting tables into separate JSON/Markdown summaries with parent-child linkage",
    "Using Small-to-Big retrieval (index concise table summary, retrieve full table markdown)"
  ],
  "drillQuestionId": "8f3a9e22-901b-42e1-88f2-bb0091aa4211"
}
```

---

### 3.4 Submit Practice Drill
* **Endpoint**: `POST /api/v1/drills/:questionId/attempt`
* **Request Body**:
```json
{
  "candidateResponse": "I will implement a Small-to-Big retrieval strategy. During ingestion, I extract the table and generate a synthetic summary of the table headers and contents to embed. When query matches this summary, the retriever fetches the full raw markdown table into the LLM prompt."
}
```
* **Response `200 OK`**:
```json
{
  "isPassed": true,
  "score": 90.0,
  "feedback": {
    "positiveHighlights": [
      "Correctly applied hierarchical / Small-to-Big chunking strategy",
      "Separated embedding index from generative context"
    ],
    "edgeCasesToConsider": [
      "Consider how you link the parent document ID in metadata for the vector store"
    ]
  },
  "unlocksVerification": true
}
```

---

### 3.5 Submit Verification Turn (Simulated Interview)
* **Endpoint**: `POST /api/v1/verifications/sessions/:id/turn`
* **Request Body**:
```json
{
  "turnIndex": 1,
  "candidateResponse": "For our RAG pipeline, we use hybrid search combining BM25 keyword matching with dense HNSW vector search, followed by a cross-encoder reranker (e.g. BGE-Reranker-Large) for top 10 documents."
}
```
* **Response `200 OK`**:
```json
{
  "turnIndex": 1,
  "turnScore": 82.5,
  "rubricBreakdown": {
    "technicalSoundness": 88,
    "tradeOffAnalysis": 78,
    "edgeCaseHandling": 80,
    "communicationClarity": 84
  },
  "interviewerFollowUp": "Good. But cross-encoder rerankers add notable inference latency. If your SLA requires P99 retrieval under 250ms on CPU, how would you optimize or replace this reranking step?",
  "hasCompletedSession": false
}
```

---

### 3.6 Candidate Readiness Index & Evidence
* **Endpoint**: `GET /api/v1/readiness/profile`
* **Response `200 OK`**:
```json
{
  "userId": "1b08ef90-7d4a-4467-bc1a-55e1008bf32e",
  "trackSlug": "genai_engineer",
  "overallReadinessScore": 76.4,
  "benchmarkComparison": {
    "entryLevelStartupBar": 75.0,
    "percentileAmongPeers": 68.5
  },
  "domainScores": [
    {
      "domainSlug": "vector_dbs_and_embeddings",
      "baseline": 35.0,
      "verifiedScore": 82.5,
      "delta": "+47.5%",
      "verifiedAt": "2026-10-12T19:30:00Z"
    }
  ]
}
```
