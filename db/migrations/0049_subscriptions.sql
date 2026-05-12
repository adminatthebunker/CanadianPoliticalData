-- Public developer API phase 1b: subscription state on private.users
-- + subscription_events idempotency log.
-- See docs/plans/public-developer-api.md for the locked spec.
--
-- Scope: dev ($20/mo) + pro ($200/mo) tiers, billed monthly. Subscriptions
-- are pure API access — they do NOT grant credits and do NOT touch
-- private.credit_ledger. The two billing systems stay orthogonal.
--
-- Cancel-at-period-end posture: when a user cancels, we set
-- private.users.cancel_at_period_end=true and keep current_plan/tier
-- intact until Stripe sends customer.subscription.deleted at the actual
-- period end. Past-due users keep their tier through Stripe's dunning
-- window (no custom grace logic — Stripe sends subscription.deleted
-- when it ultimately gives up).
--
-- Auto-promote/demote pattern: on subscription.created the webhook
-- handler runs `UPDATE private.api_keys SET tier=$plan WHERE user_id=$1
-- AND revoked_at IS NULL`. On subscription.deleted it sets tier='free'
-- the same way. This keeps api_keys.tier as the source of truth for
-- the rate-limit middleware (no per-request join to users.current_plan).

ALTER TABLE private.users
    ADD COLUMN IF NOT EXISTS current_plan text NOT NULL DEFAULT 'free'
        CHECK (current_plan IN ('free', 'dev', 'pro')),
    ADD COLUMN IF NOT EXISTS plan_status text NOT NULL DEFAULT 'inactive'
        CHECK (plan_status IN ('inactive', 'active', 'past_due', 'canceled')),
    ADD COLUMN IF NOT EXISTS stripe_subscription_id text,
    ADD COLUMN IF NOT EXISTS plan_renews_at timestamptz,
    ADD COLUMN IF NOT EXISTS plan_canceled_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancel_at_period_end boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS plan_updated_at timestamptz;

-- Partial unique index instead of UNIQUE constraint so the column can
-- be NULL on free-tier users and after subscription.deleted clears it.
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_stripe_subscription_id
    ON private.users (stripe_subscription_id)
    WHERE stripe_subscription_id IS NOT NULL;

-- Audit log for every subscription state transition. Downstream
-- idempotency layer: UNIQUE on stripe_event_id catches duplicate
-- webhook deliveries even if the upstream stripe_webhook_events
-- dedupe (PK on event id) somehow fails. Two-layer idempotency
-- mirrors the credit-pack pattern (credit_purchases.stripe_checkout_id
-- UNIQUE + credit_ledger unique partial index on (kind, reference_id)).
CREATE TABLE IF NOT EXISTS private.subscription_events (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  uuid        NOT NULL REFERENCES private.users(id) ON DELETE CASCADE,
    stripe_event_id          text        NOT NULL UNIQUE,
    event_type               text        NOT NULL
        CHECK (event_type IN ('created', 'updated', 'canceled',
                              'past_due', 'reactivated')),
    stripe_subscription_id   text,
    -- Plan transition: from_plan = previous plan ('free' on first
    -- subscribe), to_plan = new plan. Both 'free' on subscription.deleted.
    from_plan                text,
    to_plan                  text,
    -- Free-form context (cancel_at_period_end flip, status transition,
    -- plan upgrade vs renewal, etc.) — JSON shape varies by event_type.
    metadata                 jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscription_events_user_created
    ON private.subscription_events (user_id, created_at DESC);

COMMENT ON COLUMN private.users.current_plan IS
    'Current paid plan tier. free|dev|pro. Synced from Stripe via webhook.';
COMMENT ON COLUMN private.users.plan_status IS
    'inactive (no subscription), active, past_due (Stripe dunning), canceled.';
COMMENT ON COLUMN private.users.cancel_at_period_end IS
    'True when user clicked Cancel — they keep current_plan until plan_renews_at, then drop to free.';
COMMENT ON TABLE private.subscription_events IS
    'Append-only audit + downstream idempotency layer for Stripe subscription webhook events.';
