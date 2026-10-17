# Public Beta Operational Runbook: Monitoring, Backups & Rollback

This runbook defines standard operating procedures for operating the AI Interview Prep Assistant in production.

---

## 1. Health & Readiness Probes

The backend exposes two specialized endpoints:

- **Liveness Probe**: `GET /health`
  - Returns `{"status": "ok"}`
  - Used by container orchestrators to detect if process is alive.
- **Readiness Probe**: `GET /ready`
  - Returns `{"status": "ready", "service": "ai-interview-prep-assistant", "version": "0.1.0", "supabase_configured": true}`
  - Used by load balancers and deployment routers to ensure database connectivity before routing user traffic.

---

## 2. Database Migrations Procedure

All schema changes are tracked under `supabase/migrations/`.

### Applying Migrations to Supabase

1. **Via Supabase CLI**:
   ```bash
   supabase db push
   ```
2. **Via Supabase Web SQL Editor**:
   - Navigate to Supabase Dashboard > SQL Editor.
   - Run the files in order:
     - `20261013000000_create_interview_tables.sql`
     - `20261013000001_create_documents_storage_and_tables.sql`
     - `20261013000002_create_job_readiness_tables.sql`
     - `20261017000000_adaptive_interview_sessions.sql`
     - `20261017000001_security_and_rls_hardening.sql`
     - `20261018000000_beta_subscriptions_quotas.sql`

---

## 3. Database Backups & Disaster Recovery

### Automated Backups
Supabase projects have daily automated point-in-time backups enabled by default under **Database > Backups**.

### Manual Cold Backup
To generate an immediate database snapshot before major migrations:
```bash
# Using pg_dump
pg_dump --clean --if-exists --no-owner --no-privileges \
  -h db.ywllxghcfyxsmrdetvhu.supabase.co \
  -U postgres \
  -d postgres > backup_pre_migration_$(date +%Y%m%d).sql
```

### Recovery Script
A dedicated recovery script is provided at `supabase/backup_and_recovery.sql`.

---

## 4. Rollback Procedures

### Instant Frontend Rollback on Vercel
1. Go to **Vercel Dashboard > Project > Deployments**.
2. Locate the previous stable deployment.
3. Click the three dots `...` and select **Instant Rollback**.
4. Traffic is immediately redirected to the previous build in <1 second without downtime.

### Backend Container Rollback (Docker / Render / Railway)
1. **Docker Compose**:
   ```bash
   # Pull or checkout previous release tag
   git checkout tags/v0.1.0-stable
   docker compose down
   docker compose up -d --build
   ```
2. **Render / Railway**:
   - Go to Dashboard > Deploys > Click **Rollback** to the last green deploy.

---

## 5. Security & Idempotent Payment Monitoring

- All webhook transactions are logged in `public.payment_events`.
- Replay attacks are rejected using cryptographic timestamp validation and duplicate `event_id` checks.
- If a webhook fails, inspect logs:
  ```sql
  SELECT event_id, event_type, status, processed_at
  FROM public.payment_events
  ORDER BY created_at DESC
  LIMIT 20;
  ```
