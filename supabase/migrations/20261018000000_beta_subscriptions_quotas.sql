-- ==============================================================================
-- Beta Launch Migration: Subscriptions, Usage Quotas, and Idempotent Payments
-- Migration: 20261018000000_beta_subscriptions_quotas.sql
-- ==============================================================================

-- 1. Subscriptions Table
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT UNIQUE,
    plan TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro', 'enterprise')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete')),
    current_period_start TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_user_subscription UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_sub ON public.subscriptions(stripe_subscription_id);

-- 2. Usage Quotas Table
CREATE TABLE IF NOT EXISTS public.usage_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    period_start DATE NOT NULL DEFAULT CURRENT_DATE,
    interviews_taken INTEGER NOT NULL DEFAULT 0,
    interviews_limit INTEGER NOT NULL DEFAULT 5,
    tokens_consumed INTEGER NOT NULL DEFAULT 0,
    tokens_limit INTEGER NOT NULL DEFAULT 50000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_user_period_quota UNIQUE (user_id, period_start)
);

CREATE INDEX IF NOT EXISTS idx_usage_quotas_user_period ON public.usage_quotas(user_id, period_start);

-- 3. Payment Events Table (Idempotency & Replay Attack Protection)
CREATE TABLE IF NOT EXISTS public.payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT UNIQUE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'processed' CHECK (status IN ('pending', 'processed', 'failed', 'ignored')),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payment_events_event_id ON public.payment_events(event_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_idempotency_key ON public.payment_events(idempotency_key);

-- 4. Enable Row Level Security (RLS)
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_events ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies
-- Subscriptions: Authenticated users can view their own subscription
CREATE POLICY "Users can view their own subscription"
    ON public.subscriptions
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Usage Quotas: Authenticated users can view their own quotas
CREATE POLICY "Users can view their own usage quotas"
    ON public.usage_quotas
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Payment Events: Strictly private to service_role
CREATE POLICY "Service role full access to payment events"
    ON public.payment_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Service Role Full Access to Subscriptions and Quotas
CREATE POLICY "Service role full access to subscriptions"
    ON public.subscriptions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role full access to usage quotas"
    ON public.usage_quotas
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- 6. Helper Function: Check and Increment Quota
CREATE OR REPLACE FUNCTION public.check_and_increment_quota(
    p_user_id UUID,
    p_tokens INTEGER DEFAULT 0
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_plan TEXT := 'free';
    v_sub_status TEXT := 'active';
    v_interviews_limit INTEGER := 5;
    v_tokens_limit INTEGER := 50000;
    v_current_interviews INTEGER := 0;
    v_current_tokens INTEGER := 0;
    v_quota_id UUID;
BEGIN
    -- Determine user subscription plan
    SELECT plan, status INTO v_plan, v_sub_status
    FROM public.subscriptions
    WHERE user_id = p_user_id;

    IF NOT FOUND THEN
        v_plan := 'free';
        v_sub_status := 'active';
    END IF;

    -- Set limits based on active plan
    IF v_plan = 'pro' AND v_sub_status = 'active' THEN
        v_interviews_limit := 100;
        v_tokens_limit := 1000000;
    ELSIF v_plan = 'enterprise' AND v_sub_status = 'active' THEN
        v_interviews_limit := 10000;
        v_tokens_limit := 50000000;
    ELSE
        v_interviews_limit := 5;
        v_tokens_limit := 50000;
    END IF;

    -- Ensure daily quota record exists
    INSERT INTO public.usage_quotas (user_id, period_start, interviews_taken, interviews_limit, tokens_consumed, tokens_limit)
    VALUES (p_user_id, CURRENT_DATE, 0, v_interviews_limit, 0, v_tokens_limit)
    ON CONFLICT (user_id, period_start)
    DO UPDATE SET
        interviews_limit = v_interviews_limit,
        tokens_limit = v_tokens_limit,
        updated_at = now()
    RETURNING id, interviews_taken, tokens_consumed
    INTO v_quota_id, v_current_interviews, v_current_tokens;

    -- Enforce limits
    IF (v_current_interviews + 1 > v_interviews_limit) OR (v_current_tokens + p_tokens > v_tokens_limit) THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'plan', v_plan,
            'reason', 'Daily usage quota exceeded. Upgrade to Pro for high-volume access.',
            'interviews_taken', v_current_interviews,
            'interviews_limit', v_interviews_limit,
            'tokens_consumed', v_current_tokens,
            'tokens_limit', v_tokens_limit
        );
    END IF;

    -- Increment usage
    UPDATE public.usage_quotas
    SET interviews_taken = interviews_taken + 1,
        tokens_consumed = tokens_consumed + p_tokens,
        updated_at = now()
    WHERE id = v_quota_id;

    RETURN jsonb_build_object(
        'allowed', true,
        'plan', v_plan,
        'interviews_taken', v_current_interviews + 1,
        'interviews_limit', v_interviews_limit,
        'tokens_consumed', v_current_tokens + p_tokens,
        'tokens_limit', v_tokens_limit
    );
END;
$$;
