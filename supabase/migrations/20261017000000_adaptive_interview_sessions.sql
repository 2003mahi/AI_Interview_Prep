-- Supabase Migration: Adaptive AI Interviewer Support
-- Enhances interview_sessions and interview_interactions for adaptive state tracking,
-- question categories, follow-up reasoning probes, and session continuation.

ALTER TABLE public.interview_sessions 
    ADD COLUMN IF NOT EXISTS current_question_index INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS target_categories TEXT[] DEFAULT ARRAY['python', 'rag', 'llm', 'debugging', 'system_design', 'technical'],
    ADD COLUMN IF NOT EXISTS state_metadata JSONB DEFAULT '{}'::jsonb;

ALTER TABLE public.interview_interactions
    ADD COLUMN IF NOT EXISTS category TEXT,
    ADD COLUMN IF NOT EXISTS difficulty TEXT,
    ADD COLUMN IF NOT EXISTS is_followup BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS parent_question_id UUID,
    ADD COLUMN IF NOT EXISTS probe_reason TEXT,
    ADD COLUMN IF NOT EXISTS evaluation_details JSONB DEFAULT '{}'::jsonb;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_interview_sessions_user_status 
    ON public.interview_sessions(user_id, status);

CREATE INDEX IF NOT EXISTS idx_interview_interactions_session 
    ON public.interview_interactions(session_id, created_at);
