-- Supabase Migration: Job Readiness Analysis & Persistence Tables

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Job Readiness Analyses Table
CREATE TABLE IF NOT EXISTS public.job_readiness_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    job_title TEXT,
    overall_score NUMERIC(5,2) NOT NULL DEFAULT 0.00,
    analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_job_readiness_user_id ON public.job_readiness_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_job_readiness_created_at ON public.job_readiness_analyses(created_at DESC);

-- 2. Row Level Security (RLS) on public.job_readiness_analyses
ALTER TABLE public.job_readiness_analyses ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own readiness analyses"
    ON public.job_readiness_analyses FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own readiness analyses"
    ON public.job_readiness_analyses FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own readiness analyses"
    ON public.job_readiness_analyses FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own readiness analyses"
    ON public.job_readiness_analyses FOR DELETE
    USING (auth.uid() = user_id);
