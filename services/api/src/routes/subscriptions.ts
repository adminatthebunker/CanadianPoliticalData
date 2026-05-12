import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { queryOne } from "../db.js";
import { requireUser, getUser } from "../middleware/user-auth.js";
import { requireCsrf } from "../lib/csrf.js";
import {
  isConfigured as stripeConfigured,
  createSubscriptionCheckoutSession,
  createPortalSession,
  setSubscriptionCancelAtPeriodEnd,
  planPriceId,
  type SubscriptionPlan,
} from "../lib/stripe.js";
import { config } from "../config.js";

/**
 * Self-service developer-API subscription management.
 *
 * Mounted under /api/v1/me/subscriptions. All routes require
 * requireUser (session cookie auth); mutating routes additionally
 * require CSRF.
 *
 * Subscription state lives on private.users (current_plan,
 * plan_status, stripe_subscription_id, plan_renews_at,
 * cancel_at_period_end, plan_canceled_at). The webhook handler in
 * services/api/src/routes/stripe-webhook.ts is the single writer to
 * those columns; these routes only kick off Stripe-side actions and
 * read user-visible state.
 *
 * Subscriptions are PURE API ACCESS — they don't grant credits and
 * don't touch private.credit_ledger. The two billing systems are
 * deliberately orthogonal.
 */

const checkoutBody = z.object({
  plan: z.enum(["dev", "pro"]),
});

interface SubscriptionStateRow {
  current_plan: "free" | "dev" | "pro";
  plan_status: "inactive" | "active" | "past_due" | "canceled";
  stripe_subscription_id: string | null;
  stripe_customer_id: string | null;
  plan_renews_at: string | null;
  plan_canceled_at: string | null;
  cancel_at_period_end: boolean;
  plan_updated_at: string | null;
}

function planAvailable(plan: SubscriptionPlan): boolean {
  return planPriceId(plan).length > 0;
}

export default async function subscriptionsRoutes(app: FastifyInstance) {
  // ── GET /me/subscriptions ────────────────────────────────────
  // Always 200. Returns the user's current subscription state plus
  // a small `plans` catalog showing which tiers are configured on
  // this server (a price id might be unset in test mode).
  app.get("/", { preHandler: requireUser }, async (req, reply) => {
    const claims = getUser(req);
    if (!claims) return reply.code(401).send({ error: "not signed in" });

    const row = await queryOne<SubscriptionStateRow>(
      `SELECT current_plan, plan_status, stripe_subscription_id,
              stripe_customer_id, plan_renews_at, plan_canceled_at,
              cancel_at_period_end, plan_updated_at
         FROM private.users WHERE id = $1`,
      [claims.sub],
    );
    if (!row) return reply.code(404).send({ error: "user not found" });

    return reply.send({
      subscription: row,
      plans: {
        dev: { available: planAvailable("dev"), price_display: "$20/mo" },
        pro: { available: planAvailable("pro"), price_display: "$200/mo" },
      },
      stripe_enabled: stripeConfigured(),
      tax_enabled: config.stripe.taxEnabled,
    });
  });

  // ── POST /me/subscriptions/checkout ──────────────────────────
  app.post(
    "/checkout",
    {
      preHandler: [requireUser, requireCsrf],
      config: {
        rateLimit: {
          max: 5,
          timeWindow: "1 minute",
          keyGenerator: (req: import("fastify").FastifyRequest) =>
            `subscribe:${getUser(req)?.sub ?? req.ip}`,
        },
      },
    },
    async (req, reply) => {
      if (!stripeConfigured()) {
        return reply.code(503).send({ error: "stripe not configured" });
      }
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const parsed = checkoutBody.safeParse(req.body);
      if (!parsed.success) {
        return reply.code(400).send({
          error: "invalid body",
          details: parsed.error.flatten(),
        });
      }
      const { plan } = parsed.data;

      if (!planAvailable(plan)) {
        return reply.code(400).send({ error: `plan unavailable: ${plan}` });
      }

      // Refuse if user already has an active subscription. Plan changes
      // happen via the Stripe Customer Portal (POST /portal) so Stripe
      // handles the proration math. Subscribing twice would create a
      // duplicate Stripe subscription and break the one-subscription-
      // per-user invariant the webhook handler relies on.
      const existing = await queryOne<{ stripe_subscription_id: string | null; plan_status: string }>(
        `SELECT stripe_subscription_id, plan_status FROM private.users WHERE id = $1`,
        [claims.sub],
      );
      if (existing?.stripe_subscription_id && existing.plan_status === "active") {
        return reply.code(400).send({
          error: "already subscribed",
          hint: "use POST /me/subscriptions/portal to change plan",
        });
      }

      const successUrl =
        `${config.publicSiteUrl}/account/billing?subscribe=success`;
      const cancelUrl =
        `${config.publicSiteUrl}/account/billing?subscribe=cancel`;

      try {
        const { url, sessionId } = await createSubscriptionCheckoutSession({
          userId: claims.sub,
          userEmail: claims.email,
          plan,
          successUrl,
          cancelUrl,
        });
        return reply.send({ url, session_id: sessionId });
      } catch (err) {
        req.log.error({ err }, "[subscriptions] checkout session creation failed");
        return reply.code(502).send({ error: "stripe checkout failed" });
      }
    },
  );

  // ── POST /me/subscriptions/cancel ────────────────────────────
  // Sets cancel_at_period_end=true on Stripe. Webhook fires
  // customer.subscription.updated and our handler syncs the flag
  // into private.users. User keeps their tier until plan_renews_at.
  app.post(
    "/cancel",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!stripeConfigured()) {
        return reply.code(503).send({ error: "stripe not configured" });
      }
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const row = await queryOne<{
        stripe_subscription_id: string | null;
        plan_status: string;
        cancel_at_period_end: boolean;
      }>(
        `SELECT stripe_subscription_id, plan_status, cancel_at_period_end
           FROM private.users WHERE id = $1`,
        [claims.sub],
      );
      if (!row?.stripe_subscription_id || row.plan_status !== "active") {
        return reply.code(400).send({ error: "no active subscription to cancel" });
      }
      if (row.cancel_at_period_end) {
        return reply.code(200).send({ cancel_at_period_end: true, idempotent: true });
      }

      try {
        await setSubscriptionCancelAtPeriodEnd(row.stripe_subscription_id, true);
        return reply.send({ cancel_at_period_end: true });
      } catch (err) {
        req.log.error({ err }, "[subscriptions] cancel failed");
        return reply.code(502).send({ error: "stripe update failed" });
      }
    },
  );

  // ── POST /me/subscriptions/reactivate ────────────────────────
  // Undoes a pending cancellation before period end.
  app.post(
    "/reactivate",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!stripeConfigured()) {
        return reply.code(503).send({ error: "stripe not configured" });
      }
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const row = await queryOne<{
        stripe_subscription_id: string | null;
        plan_status: string;
        cancel_at_period_end: boolean;
      }>(
        `SELECT stripe_subscription_id, plan_status, cancel_at_period_end
           FROM private.users WHERE id = $1`,
        [claims.sub],
      );
      if (!row?.stripe_subscription_id) {
        return reply.code(400).send({ error: "no subscription to reactivate" });
      }
      if (!row.cancel_at_period_end) {
        return reply.code(200).send({ cancel_at_period_end: false, idempotent: true });
      }

      try {
        await setSubscriptionCancelAtPeriodEnd(row.stripe_subscription_id, false);
        return reply.send({ cancel_at_period_end: false });
      } catch (err) {
        req.log.error({ err }, "[subscriptions] reactivate failed");
        return reply.code(502).send({ error: "stripe update failed" });
      }
    },
  );

  // ── POST /me/subscriptions/portal ────────────────────────────
  // Stripe Customer Portal — self-serve card updates, invoices,
  // plan changes, payment history. We don't UI any of these; Stripe
  // hosts the surface.
  app.post(
    "/portal",
    { preHandler: [requireUser, requireCsrf] },
    async (req, reply) => {
      if (!stripeConfigured()) {
        return reply.code(503).send({ error: "stripe not configured" });
      }
      const claims = getUser(req);
      if (!claims) return reply.code(401).send({ error: "not signed in" });

      const row = await queryOne<{ stripe_customer_id: string | null }>(
        `SELECT stripe_customer_id FROM private.users WHERE id = $1`,
        [claims.sub],
      );
      if (!row?.stripe_customer_id) {
        return reply.code(400).send({
          error: "no Stripe customer yet",
          hint: "create a subscription or credit-pack purchase first",
        });
      }

      const returnUrl = `${config.publicSiteUrl}/account/billing`;
      try {
        const { url } = await createPortalSession({
          customerId: row.stripe_customer_id,
          returnUrl,
        });
        return reply.send({ url });
      } catch (err) {
        req.log.error({ err }, "[subscriptions] portal session failed");
        return reply.code(502).send({ error: "stripe portal failed" });
      }
    },
  );

}
