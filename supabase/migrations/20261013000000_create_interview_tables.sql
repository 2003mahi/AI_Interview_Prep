-- Supabase Migration: Full Interview Prep Schema with RLS and Auth Triggers

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Profiles Table linked to Supabase auth.users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    target_role TEXT,
    experience_level TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Interview Sessions Table
CREATE TABLE IF NOT EXISTS public.interview_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    experience_years INTEGER NOT NULL DEFAULT 0,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed', 'abandoned')),
    score NUMERIC(5,2),
    summary_feedback TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Interview Interactions (Questions & Answers) Table
CREATE TABLE IF NOT EXISTS public.interview_interactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES public.interview_sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    user_answer TEXT,
    feedback TEXT,
    score NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security (RLS) on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_interactions ENABLE ROW LEVEL SECURITY;

-- Profiles RLS Policies: users can only see and edit their own profile
CREATE POLICY "Profiles are viewable by owner only"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can insert their own profile"
    ON public.profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- Interview Sessions RLS Policies: enforce cross-user isolation
CREATE POLICY "Users can select their own interview sessions"
    ON public.interview_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own interview sessions"
    ON public.interview_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own interview sessions"
    ON public.interview_sessions FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own interview sessions"
    ON public.interview_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- Interview Interactions RLS Policies: verify user ownership via parent session
CREATE POLICY "Users can view interactions for their sessions only"
    ON public.interview_interactions FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = interview_interactions.session_id AND s.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert interactions for their sessions only"
    ON public.interview_interactions FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.interview_sessions s
            WHERE s.id = interview_interactions.session_id AND s.user_id = auth.uid()
        )
    );

-- Trigger: Automatically create a profile when a new user signs up in auth.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (
        new.id,
        new.email,
        new.raw_user_meta_data->>'full_name'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
