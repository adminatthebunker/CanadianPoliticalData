-- Extend subscription_events.event_type to record admin-initiated
-- plan grants distinctly from Stripe-driven 'created' / 'updated' /
-- 'canceled' transitions. Admin grants do not have a real Stripe
-- event id, so we synthesize one ('admin:<grant_uuid>') and tag the
-- row with event_type='admin_grant' for grep-ability.

ALTER TABLE private.subscription_events
    DROP CONSTRAINT IF EXISTS subscription_events_event_type_check;

ALTER TABLE private.subscription_events
    ADD CONSTRAINT subscription_events_event_type_check
        CHECK (event_type IN ('created', 'updated', 'canceled',
                              'past_due', 'reactivated', 'admin_grant'));
