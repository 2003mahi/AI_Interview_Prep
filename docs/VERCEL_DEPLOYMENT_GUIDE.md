# Complete Zero-Error Vercel Deployment Guide

This guide ensures **100% successful deployment** of the AI Interview Prep Assistant on Vercel with **zero wasted tokens/credits**, zero build errors, and production-grade security.

---

## 1. Architecture Overview for Vercel

```
┌──────────────────────────────────────────────┐
│            Vercel Edge Network               │
│  Next.js 16 App Router (React 19 Frontend)  │
│  - Static & Dynamic SSR Pages                │
│  - Zero-token client-side rubric banks       │
└──────────────┬───────────────────────────────┘
               │
       ┌───────┴──────────────────────┐
       ▼                              ▼
┌───────────────────────────┐  ┌───────────────────────────┐
│     Supabase Cloud        │  │     FastAPI Backend       │
│  - Auth (OAuth / JWT)     │  │  - Adaptive Interview API │
│  - PostgreSQL RLS Tables  │  │  - Document Ingestion     │
│  - Subscriptions & Quotas │  │  - Idempotent Webhooks    │
│  - Storage Buckets        │  │  - Hosted (Render/Fly/Koyeb)
└───────────────────────────┘  └───────────────────────────┘
```

---

## 2. Token & Credit Cost-Optimization Strategy

Deploying AI applications can quickly burn through OpenAI / Anthropic credits unless guarded. This codebase includes built-in safeguards:

1. **Role Question Bank (Zero LLM Tokens)**:
   - Built-in multi-tier question banks for Senior Full Stack, Backend & Distributed Systems, and AI/ML Systems Engineers.
   - Saves 100% of LLM generation tokens for standard interview questions.
2. **Client-Side Intelligent Audit Fallback**:
   - If the backend is waking up from a cold start, the frontend smoothly delivers client-side evaluation rubrics without showing blank screens or errors.
3. **Daily User Quotas**:
   - Free users are capped at **5 interviews and 50,000 tokens per day**.
   - Atomic database stored procedure (`check_and_increment_quota`) prevents credit exhaustion.

---

## 3. Step-by-Step Vercel Deployment

### Method A: Deploy via GitHub (Recommended)

1. **Push your code to GitHub**:
   ```bash
   git add .
   git commit -m "feat: beta release readiness & vercel configuration"
   git push origin main
   ```

2. **Import to Vercel**:
   - Go to [vercel.com/new](https://vercel.com/new).
   - Select your GitHub repository.

3. **Configure Project Settings**:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: Click `Edit` and select `frontend` (Or leave as `./` because root `vercel.json` is pre-configured).
   - **Build Command**: `next build` (default)
   - **Output Directory**: `.next` (default)
   - **Install Command**: `npm install` (default)

4. **Environment Variables**:
   Under **Environment Variables**, add the following:

   | Key | Value Description | Example / Location |
   | :--- | :--- | :--- |
   | `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase Project URL | `https://ywllxghcfyxsmrdetvhu.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Anonymous Public Key | Obtain from Supabase Dashboard > Settings > API |
   | `NEXT_PUBLIC_BACKEND_URL` | Public URL of your deployed FastAPI backend | `https://your-backend.onrender.com` |

5. **Deploy**:
   - Click **Deploy**. The build will complete in ~20-30 seconds with Exit Code 0.

---

## 4. Backend Deployment (Complementary to Vercel)

Because FastAPI is Python-based with async background jobs, host the backend on a low-cost or free container platform:

### Deploying Backend to Render / Railway / Fly.io

1. **Render.com (Web Service)**:
   - Root Directory: `backend`
   - Runtime: `Docker` (or Python 3.12, Build: `pip install -r requirements.txt`, Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`)
   - Add Environment Variables from `backend/.env.example`.
2. **Copy the Render backend URL** (e.g., `https://ai-interview-backend.onrender.com`).
3. **Update Vercel**: Set `NEXT_PUBLIC_BACKEND_URL` in your Vercel project settings to this Render URL.

---

## 5. Preventing Common Deployment Issues

| Issue | Cause | Fix Implemented |
| :--- | :--- | :--- |
| **CORS blocked on Vercel preview URLs** | Backend only permitted `localhost:3000` | Backend `CORSMiddleware` now supports `allow_origin_regex=r"^https://.*\.vercel\.app$"` automatically |
| **Hardcoded `localhost:8000`** | Static fetch strings in components | Updated to dynamic `process.env.NEXT_PUBLIC_BACKEND_URL` with resilient fallback |
| **Heavy Docker Images** | Copying `.next` or `node_modules` | Created `.dockerignore` files for both frontend and backend |
| **TypeScript / Turbopack build failure** | Next 16 experimental syntax errors | Verified and passed with `npm run build` (Exit code 0) |
