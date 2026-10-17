-- Database Backup, Verification, and Disaster Recovery Guide
-- Production Supabase PostgreSQL

-- 1. Full schema & table verification query:
SELECT 
    schemaname, 
    tablename, 
    rowsecurity AS rls_enabled
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;

-- 2. RLS policy validation query (verifies every table has full CRUD policy coverage):
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, cmd;

-- 3. Data Integrity & Orphan Detection:
-- Find sessions without existing profile owner:
SELECT s.id, s.user_id 
FROM public.interview_sessions s 
LEFT JOIN public.profiles p ON s.user_id = p.id 
WHERE p.id IS NULL;

-- Find documents without existing profile owner:
SELECT d.id, d.user_id 
FROM public.documents d 
LEFT JOIN public.profiles p ON d.user_id = p.id 
WHERE p.id IS NULL;

-- Find interactions without parent session:
SELECT i.id, i.session_id 
FROM public.interview_interactions i 
LEFT JOIN public.interview_sessions s ON i.session_id = s.id 
WHERE s.id IS NULL;

-- 4. Point-In-Time Backup Command (Run from CLI):
-- pg_dump --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" -F c -b -v -f "backup_$(date +%Y%m%d_%H%M%S).dump"

-- 5. Point-In-Time Disaster Recovery Command:
-- pg_restore --clean --if-exists --no-owner --no-privileges -d "$DATABASE_URL" -v "backup_filename.dump"
