import type { FastifyInstance } from "fastify";
import type Stripe from "stripe";
import { query, pool } from "../db.js";
import {
  isConfigured as stripeIsConfigured,
  constructWebhookEvent,
  getPackBySku,
  priceIdToPlan,
  type SubscriptionPlan,
} from "../lib/stripe.js";
import { grantStripePurchase } from "../lib/credits.js";

/**
 * Stripe webhook handler — POST /webhooks/stripe.
 *
 * Plugin-scoped raw-body parser: Stripe signs the raw request bytes,
 * so Fastify's default JSON body parser would break verification by
 * reserialising. Fastify's encapsulation scopes the content-type
 * parser below to routes registered inside this plugin only — other
 * routes continue to receive parsed JSON objects.
 *
 * Two idempotency layers cooperate here:
 *   1. `stripe_webhook_events` PK on event.id drops duplicate
 *      deliveries at the front door. Second receipt of an event we've
 *      already processed succeeds (return 200, no-op).
 *   2. `uniq_credit_ledger_kind_ref` on (kind, reference_id) is the
 *      belt-and-braces layer: even if the event table check somehow
 *      let a dupe through, a single Stripe checkout cannot grant
 *      credits twice.
 *
 * We ALWAYS return 200 on successfully-ingested events — including
 * events we choose to ignore (unrecognised types). Stripe retries on
 * non-2xx for up to 3 days; returning non-200 for "I don't care about
 * this event type" would burn their retry queue.
 *
 * On signature failure we return 400: the request isn't Stripe, so
 * there's nothing to retry. The raw-body check happens BEFORE any DB
 * write; unsigned / malformed events never touch the ledger.
 */

export default async function stripeWebhookRoutes(app: FastifyInstance) {
  // Raw-body JSON parser scoped to this plugin only. Fastify's
  // encapsulation means routes registered outside this function still
  // get the default application/json parser.
  app.addContentTypeParser(
    "application/json",
    { parseAs: "buffer" },
    (_req, body, done) => {
      done(null, body);
    }
  );

  app.post("/", async (req, reply) => {
    if (!stripeIsConfigured()) {
      // Return 200 (not 5xx) so Stripe stops retrying while we're
      // misconfigured. Stripe retries 5xx responses for up to 72
      // hours, which would burn through their retry budget without
      // any hope of success. The operator-facing warning lives in
      // config.ts's startup log, not here.
      req.log.warn({}, "[stripe-webhook] received event but Stripe not configured; discarding");
      return reply.code(200).send({ received: false, reason: "stripe not configured" });
    }

    const signature = req.headers["stripe-signature"];
    if (!signature || typeof signature !== "string") {
      return reply.code(400).send({ error: "missing stripe-signature header" });
    }

    const rawBody = req.body as Buffer;
    if (!Buffer.isBuffer(rawBody)) {
      req.log.error({ type: typeof req.body }, "[stripe-webhook] raw body parser did not produce a Buffer");
      return reply.code(500).send({ error: "internal body parser error" });
    }

    let event: Stripe.Event;
    try {
      event = constructWebhookEvent(rawBody, signature);
    } catch (err) {
      req.log.warn({ err }, "[stripe-webhook] signature verification failed");
      return reply.code(400).send({ error: "signature verification failed" });
    }

    // Upstream dedup: record the event id. PK violation means we've
    // already seen this event — return 200 without reprocessing.
    try {
      await query(
        `INSERT INTO private.stripe_webhook_events (id, type, raw_payload)
             VALUES ($1, $2, $3)`,
        [event.id, event.type, JSON.stringify(event)]
      );
    } catch (err) {
      // Duplicate PK is the expected happy-path for retries.
      const code = (err as { code?: string }).code;
      if (code === "23505") {
        req.log.info({ event_id: event.id, type: event.type }, "[stripe-webhook] duplicate event, already processed");
        return reply.send({ received: true, duplicate: true });
      }
      req.log.error({ err, event_id: event.id }, "[stripe-webhook] failed to record event");
      return reply.code(500).send({ error: "failed to record event" });
    }

    try {
      await dispatchEvent(req, event);
      await query(
        `UPDATE private.stripe_webhook_events SET processed_at = now() WHERE id = $1`,
        [event.id]
      );
      return reply.send({ received: true });
    } catch (err) {
      // Record the failure so the admin can investigate without
      // losing the event payload. Return non-200 to trigger Stripe's
      // retry — the PK prevents duplicate rows, but retries let us
      // recover after a transient DB / upstream failure.
      const message = err instanceof Error ? err.message : String(err);
      await query(
        `UPDATE private.stripe_webhook_events SET error_message = $2 WHERE id = $1`,
        [event.id, message.slice(0, 1000)]
      );
      req.log.error({ err, event_id: event.id, type: event.type }, "[stripe-webhook] handler failed");
      return reply.code(500).send({ error: "handler failed" });
    }
  });
}

type WebhookLog = {
  log: {
    info: (obj: object, msg: string) => void;
    warn: (obj: object, msg: string) => void;
  };
};

async function dispatchEvent(
  req: WebhookLog,
  event: Stripe.Event
): Promise<void> {
  switch (event.type) {
    case "checkout.session.completed":
      await handleCheckoutCompleted(req, event);
      return;

    // Public dev-API subscription lifecycle (phase 1b). The
    // checkout.session.completed event also fires for subscription
    // mode but we let the dedicated subscription events drive the
    // state machine — they carry the authoritative subscription
    // object directly.
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
      await handleSubscriptionEvent(req, event);
      return;

    // Ignored but acknowledged 200 so Stripe stops retrying.
    default:
      req.log.info({ type: event.type, id: event.id }, "[stripe-webhook] ignoring event type");
      return;
  }
}

async function handleCheckoutCompleted(
  req: { log: { info: (obj: object, msg: string) => void; warn: (obj: object, msg: string) => void } },
  event: Stripe.Event
): Promise<void> {
  const session = event.data.object as Stripe.Checkout.Session;

  // One-time payment packs only — subscription checkouts land through
  // a different handler (not yet written).
  if (session.mode !== "payment") {
    req.log.info({ mode: session.mode, session_id: session.id }, "[stripe-webhook] ignoring non-payment checkout");
    return;
  }

  const userId = session.client_reference_id ?? session.metadata?.user_id;
  if (!userId) {
    req.log.warn({ session_id: session.id }, "[stripe-webhook] checkout session missing user_id");
    throw new Error(`session ${session.id} has no user reference`);
  }

  // SECURITY: the credit amount MUST come from the server-side catalog
  // keyed on the session's sku, not from session.metadata.credits. A
  // Stripe Dashboard operator can edit pending-session metadata freely
  // (Stripe signs the event after delivery, so signature validation
  // does NOT protect against tampered metadata). We read the sku from
  // metadata, then look up the authoritative credit count from
  // PACK_CREDITS server-side. Any mismatch between the two is logged
  // and the catalog value wins. An unknown sku hard-fails — we never
  // guess.
  const metadataSku = session.metadata?.sku;
  if (!metadataSku) {
    throw new Error(`session ${session.id} missing sku metadata`);
  }
  const pack = getPackBySku(metadataSku);
  if (!pack) {
    throw new Error(`session ${session.id} has unknown sku: ${metadataSku}`);
  }
  const credits = pack.credits;

  // Informational: detect tampering. The metadata field has no
  // authority over the grant, but a mismatch here is a strong signal
  // that someone edited a session in the Stripe dashboard.
  const metadataCredits = session.metadata?.credits;
  if (metadataCredits !== undefined) {
    const parsed = Number.parseInt(metadataCredits, 10);
    if (Number.isFinite(parsed) && parsed !== pack.credits) {
      req.log.warn(
        {
          session_id: session.id,
          metadata_credits: parsed,
          catalog_credits: pack.credits,
          sku: metadataSku,
        },
        "[stripe-webhook] metadata credits disagrees with catalog — using catalog (possible dashboard tamper)"
      );
    }
  }

  const amountCents = session.amount_total ?? 0;
  const currency = session.currency ?? "cad";
  const paymentIntentId =
    typeof session.payment_intent === "string" ? session.payment_intent : null;

  try {
    await grantStripePurchase({
      userId,
      stripeCheckoutId: session.id,
      stripePaymentIntentId: paymentIntentId,
      amountCents,
      currency,
      credits,
      rawWebhook: event,
    });
    req.log.info(
      { user_id: userId, session_id: session.id, credits },
      "[stripe-webhook] credits granted"
    );
  } catch (err) {
    // Downstream dedup layer fired: the ledger already has a row for
    // this checkout id. Treat as success — the purchase landed on an
    // earlier delivery.
    const code = (err as { code?: string }).code;
    if (code === "23505") {
      req.log.info(
        { session_id: session.id },
        "[stripe-webhook] ledger already has entry for this checkout, skipping"
      );
      return;
    }
    throw err;
  }
}

/**
 * Subscription lifecycle handler. Backs all three of:
 *   - customer.subscription.created   (first subscribe / re-subscribe)
 *   - customer.subscription.updated   (plan change, cancel-at-period-end
 *                                       toggle, status transition)
 *   - customer.subscription.deleted   (subscription has actually ended)
 *
 * Resolves the user via stripe_customer_id lookup. All sync writes
 * (subscription_events audit + private.users state + api_keys.tier
 * auto-promote/demote) happen in one DB transaction so partial state
 * is impossible. Downstream idempotency: UNIQUE on
 * subscription_events.stripe_event_id catches double-deliveries even
 * if the upstream stripe_webhook_events PK dedupe somehow misses.
 *
 * Auto-promote: on subscribe (or upgrade), every non-revoked api_key
 * for the user gets tier=$plan. On subscription.deleted, every
 * non-revoked api_key gets tier='free'. This keeps api_keys.tier as
 * the source of truth for the rate-limit middleware — no per-request
 * join to users.current_plan.
 *
 * cancel_at_period_end is NOT a demotion trigger. The user keeps
 * their tier until subscription.deleted actually fires at period end.
 * past_due is also not a demotion trigger; Stripe handles dunning
 * and ultimately fires subscription.deleted if the customer can't
 * pay.
 */
async function handleSubscriptionEvent(
  req: WebhookLog,
  event: Stripe.Event,
): Promise<void> {
  const sub = event.data.object as Stripe.Subscription;
  const customerId = typeof sub.customer === "string"
    ? sub.customer
    : sub.customer.id;

  const userRow = await query<{ id: string; current_plan: string }>(
    `SELECT id::text, current_plan
       FROM private.users WHERE stripe_customer_id = $1`,
    [customerId],
  );
  const user = userRow[0];
  if (!user) {
    req.log.warn(
      { customer_id: customerId, event_id: event.id, event_type: event.type },
      "[stripe-webhook] subscription event for unknown customer; ignoring",
    );
    return;
  }

  // Resolve target plan from the subscription's first price item.
  // subscription.items.data[0].price.id should always be present;
  // missing is a hard error (stripe sent us a malformed event).
  const priceId = sub.items.data[0]?.price.id;
  let plan: SubscriptionPlan | "free";
  if (event.type === "customer.subscription.deleted") {
    plan = "free";
  } else {
    const resolved = priceId ? priceIdToPlan(priceId) : null;
    if (!resolved) {
      req.log.warn(
        { event_id: event.id, price_id: priceId, customer_id: customerId },
        "[stripe-webhook] subscription event with unknown price id; ignoring",
      );
      return;
    }
    plan = resolved;
  }

  // Map Stripe status → our four-state enum. `incomplete` /
  // `incomplete_expired` map to inactive (the subscribe attempt failed
  // before the first payment); `unpaid` is treated as past_due.
  let planStatus: "active" | "past_due" | "canceled" | "inactive";
  if (event.type === "customer.subscription.deleted") {
    planStatus = "canceled";
  } else if (sub.status === "active" || sub.status === "trialing") {
    planStatus = "active";
  } else if (sub.status === "past_due" || sub.status === "unpaid") {
    planStatus = "past_due";
  } else if (sub.status === "canceled") {
    planStatus = "canceled";
  } else {
    planStatus = "inactive";
  }

  // current_period_end moved off the Subscription object onto each
  // SubscriptionItem in newer Stripe API versions. Read it from the
  // first item — for our single-item subscriptions (one plan price)
  // these are equivalent.
  const periodEnd = sub.items.data[0]?.current_period_end;
  const renewsAt = periodEnd
    ? new Date(periodEnd * 1000).toISOString()
    : null;
  const cancelAtPeriodEnd = Boolean(sub.cancel_at_period_end);

  const eventTypeShort: "created" | "updated" | "canceled" =
    event.type === "customer.subscription.created" ? "created"
    : event.type === "customer.subscription.deleted" ? "canceled"
    : "updated";

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Downstream idempotency: UNIQUE on stripe_event_id. If we hit
    // 23505 here, this exact event was already processed (likely an
    // out-of-order or post-failure retry that the upstream PK dedupe
    // didn't catch); just commit the no-op transaction and return.
    try {
      await client.query(
        `INSERT INTO private.subscription_events
              (user_id, stripe_event_id, event_type,
               stripe_subscription_id, from_plan, to_plan, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)`,
        [
          user.id,
          event.id,
          eventTypeShort,
          sub.id,
          user.current_plan,
          plan,
          JSON.stringify({
            stripe_status: sub.status,
            cancel_at_period_end: cancelAtPeriodEnd,
            current_period_end: periodEnd,
          }),
        ],
      );
    } catch (err) {
      const code = (err as { code?: string }).code;
      if (code === "23505") {
        await client.query("ROLLBACK");
        req.log.info(
          { event_id: event.id, type: event.type },
          "[stripe-webhook] subscription_event already recorded, skipping sync",
        );
        return;
      }
      throw err;
    }

    if (event.type === "customer.subscription.deleted") {
      // Hard demote. Clear all subscription state on the user; flip
      // every non-revoked api_key back to 'free'.
      await client.query(
        `UPDATE private.users
            SET current_plan          = 'free',
                plan_status           = 'canceled',
                plan_canceled_at      = now(),
                stripe_subscription_id = NULL,
                plan_renews_at        = NULL,
                cancel_at_period_end  = false,
                plan_updated_at       = now()
          WHERE id = $1`,
        [user.id],
      );
      await client.query(
        `UPDATE private.api_keys
            SET tier = 'free',
                updated_at = now()
          WHERE user_id = $1 AND revoked_at IS NULL AND tier != 'free'`,
        [user.id],
      );
    } else {
      // created / updated. Sync the user row in full.
      await client.query(
        `UPDATE private.users
            SET current_plan          = $2,
                plan_status           = $3,
                stripe_subscription_id = $4,
                plan_renews_at        = $5::timestamptz,
                cancel_at_period_end  = $6,
                plan_updated_at       = now(),
                plan_canceled_at      = NULL
          WHERE id = $1`,
        [user.id, plan, planStatus, sub.id, renewsAt, cancelAtPeriodEnd],
      );

      // Auto-promote: only if the subscription is currently providing
      // service (active/past_due/inactive-but-not-canceled). Past-due
      // intentionally keeps the tier — Stripe handles dunning, and a
      // successful retry restores 'active' without churning the keys.
      if (planStatus === "active" || planStatus === "past_due") {
        await client.query(
          `UPDATE private.api_keys
              SET tier = $2,
                  updated_at = now()
            WHERE user_id = $1 AND revoked_at IS NULL AND tier != $2`,
          [user.id, plan],
        );
      }
    }

    await client.query("COMMIT");
    req.log.info(
      {
        user_id: user.id, event_type: event.type,
        from_plan: user.current_plan, to_plan: plan,
        plan_status: planStatus,
        cancel_at_period_end: cancelAtPeriodEnd,
      },
      "[stripe-webhook] subscription state synced",
    );
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

/**
 * Ensure we also see the validation type for the checkout ignored
 * branches above. Exporting nothing runtime-visible, just to keep the
 * tsc diagnostic surface honest.
 */
export type { Stripe };
