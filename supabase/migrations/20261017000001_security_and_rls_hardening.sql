-- Supabase Migration: Security and Row-Level Security (RLS) Hardening
-- 1. Complete missing RLS policies for interview_interactions (UPDATE and DELETE)
-- 2. Force RLS across all candidate data tables
-- 3. Secure function search_paths against search_path hijacking

-- 1. Missing interview_interactions policies
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'interview_interactions' AND policyname = 'Users can update interactions for their sessions only'
    ) THEN
        CREATE POLICY "Users can update interactions for their sessions only"
            ON public.interview_interactions FOR UPDATE
            USING (
                EXISTS (
                    SELECT 1 FROM public.interview_sessions s
                    WHERE s.id = interview_interactions.session_id AND s.user_id = auth.uid()
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'interview_interactions' AND policyname = 'Users can delete interactions for their sessions only'
    ) THEN
        CREATE POLICY "Users can delete interactions for their sessions only"
            ON public.interview_interactions FOR DELETE
            USING (
                EXISTS (
                    SELECT 1 FROM public.interview_sessions s
                    WHERE s.id = interview_interactions.session_id AND s.user_id = auth.uid()
                )
            );
    END IF;
END $$;

-- 2. Force Row Level Security (ensures table owners/roles with bypass privileges still respect RLS where required)
ALTER TABLE public.profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE public.interview_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.interview_interactions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.documents FORCE ROW LEVEL SECURITY;
ALTER TABLE public.job_readiness_analyses FORCE ROW LEVEL SECURITY;

-- 3. Secure search_path on auth trigger function
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name)
    VALUES (
        new.id,
        new.email,
        new.raw_user_meta_data->>'full_name'
    )
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        full_name = COALESCE(EXCLUDED.full_name, public.profiles.full_name),
        updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;
