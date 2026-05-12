import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { userFetch } from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

interface SubscriptionState {
  current_plan: "free" | "dev" | "pro";
  plan_status: "inactive" | "active" | "past_due" | "canceled";
  stripe_subscription_id: string | null;
  stripe_customer_id: string | null;
  plan_renews_at: string | null;
  plan_canceled_at: string | null;
  cancel_at_period_end: boolean;
  plan_updated_at: string | null;
}

interface SubscriptionsResponse {
  subscription: SubscriptionState;
  plans: {
    dev: { available: boolean; price_display: string };
    pro: { available: boolean; price_display: string };
  };
  stripe_enabled: boolean;
  tax_enabled: boolean;
}

const TIER_LIMITS: Record<"free" | "dev" | "pro", string> = {
  free: "60 requests / hour",
  dev: "1,000 requests / hour",
  pro: "10,000 requests / hour",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "long", day: "numeric",
  });
}

function statusChip(s: SubscriptionState): { label: string; cls: string } {
  if (s.current_plan === "free") {
    return { label: "Free tier", cls: "cpd-auth__chip--muted" };
  }
  if (s.plan_status === "past_due") {
    return { label: "Payment past due", cls: "cpd-auth__chip--warn" };
  }
  if (s.cancel_at_period_end) {
    return {
      label: `Canceling on ${fmtDate(s.plan_renews_at)}`,
      cls: "cpd-auth__chip--warn",
    };
  }
  if (s.plan_status === "active") {
    return { label: "Active", cls: "cpd-auth__chip--ok" };
  }
  return { label: s.plan_status, cls: "cpd-auth__chip--muted" };
}

/**
 * /account/billing — Stripe subscription management for the public
 * developer API tiers (dev $20/mo, pro $200/mo). Backed by
 * /api/v1/me/subscriptions (services/api/src/routes/subscriptions.ts).
 *
 * Subscription state lives on private.users; this page never writes
 * directly. Subscribe/cancel/reactivate kick off Stripe-side actions
 * and the webhook handler syncs results back into the user row.
 *
 * Subscriptions auto-promote ALL of the user's API keys to the plan's
 * tier (UPDATE private.api_keys ... in the webhook handler). Users
 * don't need to mint new keys — existing integrations just get higher
 * rate limits.
 */
export default function BillingPage() {
  useDocumentTitle("Billing · Canadian Political Data");
  const { user, loading: authLoading, disabled } = useUserAuth();
  const [searchParams] = useSearchParams();
  const [data, setData] = useState<SubscriptionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"checkout" | "cancel" | "reactivate" | "portal" | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await userFetch<SubscriptionsResponse>("/me/subscriptions");
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

  // ?subscribe=success → re-fetch after a short delay so the post-webhook
  // state lands. Stripe usually delivers the subscription.created event
  // within a couple seconds of payment confirmation.
  useEffect(() => {
    if (searchParams.get("subscribe") === "success") {
      const t = setTimeout(() => { void load(); }, 2000);
      return () => clearTimeout(t);
    }
  }, [searchParams, load]);

  if (authLoading) return <section className="cpd-auth"><p>Loading…</p></section>;
  if (disabled) {
    return (
      <section className="cpd-auth">
        <h2>Accounts unavailable</h2>
        <p>User accounts are not configured on this server.</p>
      </section>
    );
  }
  if (!user) {
    return (
      <section className="cpd-auth">
        <h2>Sign in to manage billing</h2>
        <p><Link to="/login?from=/account/billing">Sign in →</Link></p>
      </section>
    );
  }

  async function onSubscribe(plan: "dev" | "pro") {
    setBusy("checkout");
    setError(null);
    try {
      const res = await userFetch<{ url: string }>(
        "/me/subscriptions/checkout",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan }),
        },
      );
      window.location.assign(res.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Subscribe failed.");
      setBusy(null);
    }
  }

  async function onCancel() {
    if (!confirm(
      `Cancel subscription? You'll keep your current tier until ${fmtDate(data?.subscription.plan_renews_at ?? null)}, ` +
      "then drop to the free tier (60 requests/hour). You can reactivate anytime before then."
    )) return;
    setBusy("cancel");
    setError(null);
    try {
      await userFetch<void>("/me/subscriptions/cancel", { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed.");
    } finally {
      setBusy(null);
    }
  }

  async function onReactivate() {
    setBusy("reactivate");
    setError(null);
    try {
      await userFetch<void>("/me/subscriptions/reactivate", { method: "POST" });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reactivate failed.");
    } finally {
      setBusy(null);
    }
  }

  async function onPortal() {
    setBusy("portal");
    setError(null);
    try {
      const res = await userFetch<{ url: string }>(
        "/me/subscriptions/portal",
        { method: "POST" },
      );
      window.location.assign(res.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Portal failed.");
      setBusy(null);
    }
  }

  if (loading && !data) {
    return <section className="cpd-auth"><p>Loading subscription…</p></section>;
  }
  if (!data) {
    return (
      <section className="cpd-auth">
        <h2>Billing</h2>
        {error && <p className="cpd-auth__error" role="alert">{error}</p>}
      </section>
    );
  }
  if (!data.stripe_enabled) {
    return (
      <section className="cpd-auth">
        <h2>Billing</h2>
        <p>Subscriptions are not enabled on this server.</p>
      </section>
    );
  }

  const sub = data.subscription;
  const status = statusChip(sub);
  const isActiveOrPastDue = sub.plan_status === "active" || sub.plan_status === "past_due";

  return (
    <section className="cpd-auth">
      <h2>Billing</h2>
      <p className="cpd-auth__sub">
        Subscriptions for the public developer API. Tier limits apply to
        all of your <Link to="/account/api-keys">API keys</Link> automatically
        — when you subscribe, every existing key gets the new rate limit
        without needing to be re-minted.
      </p>

      {error && <p className="cpd-auth__error" role="alert">{error}</p>}

      {searchParams.get("subscribe") === "cancel" && (
        <p className="cpd-auth__notice">
          Subscribe canceled. No payment was taken.
        </p>
      )}

      {/* Current state card */}
      <div className="cpd-auth__notice" style={{ marginTop: "1rem" }}>
        <h3>
          Current plan:{" "}
          <span className={`cpd-auth__chip ${status.cls}`}>{status.label}</span>
        </h3>
        <p>
          <strong>{sub.current_plan === "free" ? "Free" : sub.current_plan.toUpperCase()}</strong>
          {" — "}
          {TIER_LIMITS[sub.current_plan]}.
          {sub.plan_renews_at && !sub.cancel_at_period_end && (
            <> Renews on <strong>{fmtDate(sub.plan_renews_at)}</strong>.</>
          )}
          {sub.cancel_at_period_end && sub.plan_renews_at && (
            <> Will downgrade to free on <strong>{fmtDate(sub.plan_renews_at)}</strong>.</>
          )}
          {sub.plan_status === "past_due" && (
            <> Payment is past due — please <button type="button" onClick={onPortal} disabled={busy !== null}>update your card</button>.</>
          )}
        </p>
        {isActiveOrPastDue && (
          <div className="cpd-auth__row">
            <button type="button" onClick={onPortal} disabled={busy !== null}>
              {busy === "portal" ? "Opening…" : "Manage subscription (Stripe)"}
            </button>
            {!sub.cancel_at_period_end && (
              <button
                type="button"
                className="cpd-auth__signout"
                onClick={onCancel}
                disabled={busy !== null}
              >
                {busy === "cancel" ? "Canceling…" : "Cancel subscription"}
              </button>
            )}
            {sub.cancel_at_period_end && (
              <button
                type="button"
                onClick={onReactivate}
                disabled={busy !== null}
              >
                {busy === "reactivate" ? "Reactivating…" : "Reactivate subscription"}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Plan picker — only show plans available on this server */}
      {sub.current_plan === "free" && (
        <section className="admin__section">
          <h3>Upgrade your tier</h3>
          {data.tax_enabled && (
            <p className="cpd-auth__sub">
              Prices below are exclusive of tax. Applicable Canadian sales
              tax (GST/HST/PST) will be calculated and added at checkout
              based on your billing address.
            </p>
          )}
          <div className="cpd-auth__tiles" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {data.plans.dev.available && (
              <article className="cpd-auth__tile">
                <h4 className="cpd-auth__tile-title">
                  Developer <span className="cpd-auth__tile-chip">{data.plans.dev.price_display}</span>
                </h4>
                <p className="cpd-auth__tile-sub">
                  {TIER_LIMITS.dev}. Per key. All your existing API keys
                  get the new limit automatically.
                </p>
                <button
                  type="button"
                  onClick={() => onSubscribe("dev")}
                  disabled={busy !== null}
                >
                  {busy === "checkout" ? "Redirecting…" : "Subscribe to Developer"}
                </button>
              </article>
            )}
            {data.plans.pro.available && (
              <article className="cpd-auth__tile">
                <h4 className="cpd-auth__tile-title">
                  Pro <span className="cpd-auth__tile-chip">{data.plans.pro.price_display}</span>
                </h4>
                <p className="cpd-auth__tile-sub">
                  {TIER_LIMITS.pro}. Per key. Ideal for production apps
                  and bulk research workflows.
                </p>
                <button
                  type="button"
                  onClick={() => onSubscribe("pro")}
                  disabled={busy !== null}
                >
                  {busy === "checkout" ? "Redirecting…" : "Subscribe to Pro"}
                </button>
              </article>
            )}
          </div>
          {!data.plans.dev.available && !data.plans.pro.available && (
            <p className="cpd-auth__sub">
              No subscription plans are currently configured on this server.
            </p>
          )}
        </section>
      )}

      {/* Plan upgrade option for existing subscribers (dev → pro) */}
      {isActiveOrPastDue && sub.current_plan === "dev" && data.plans.pro.available && (
        <section className="admin__section">
          <h3>Upgrade to Pro</h3>
          <p className="cpd-auth__sub">
            Stripe will prorate the charge automatically. Use the
            "Manage subscription" button above to change your plan.
          </p>
        </section>
      )}
    </section>
  );
}
