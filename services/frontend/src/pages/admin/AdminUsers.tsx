import { FormEvent, useCallback, useEffect, useState } from "react";
import { adminFetch } from "../../api";
import { useAdminFetch } from "../../hooks/useAdminFetch";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../styles/admin.css";

/**
 * /admin/users — user picker, per-user balance + ledger, credit grant
 * (comp flow), rate-limit tier adjustment, and the pending-request
 * queue for rate-limit increases.
 *
 * Scope is intentionally narrow: admin operations that belong to the
 * billing rail. Not a general-purpose user directory. If that becomes
 * a need, split it into a separate page.
 */

type RateLimitTier = "default" | "extended" | "unlimited" | "suspended";
type Plan = "free" | "dev" | "pro";
type PlanStatus = "inactive" | "active" | "past_due" | "canceled";

interface UserRow {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  rate_limit_tier: RateLimitTier;
  stripe_customer_id: string | null;
  created_at: string;
  last_login_at: string | null;
  current_plan: Plan;
  plan_status: PlanStatus;
  // Detail-only fields — null on list rows
  stripe_subscription_id?: string | null;
  plan_renews_at?: string | null;
  cancel_at_period_end?: boolean;
  plan_updated_at?: string | null;
}

interface LedgerEntry {
  id: string;
  delta: number;
  state: "pending" | "held" | "committed" | "refunded";
  kind:
    | "stripe_purchase"
    | "admin_credit"
    | "correction_reward"
    | "report_hold"
    | "report_commit"
    | "report_refund";
  reference_id: string | null;
  reason: string | null;
  created_at: string;
}

interface SubscriptionEvent {
  id: string;
  event_type: "created" | "updated" | "canceled" | "past_due" | "reactivated" | "admin_grant";
  from_plan: string | null;
  to_plan: string | null;
  stripe_subscription_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

interface UserDetail {
  user: UserRow;
  balance: number;
  ledger: LedgerEntry[];
  subscription_events: SubscriptionEvent[];
}

interface RateLimitRequest {
  id: string;
  user_id: string;
  email: string;
  reason: string;
  requested_tier: "extended" | "unlimited";
  status: "pending" | "approved" | "denied";
  admin_response: string | null;
  created_at: string;
  resolved_at: string | null;
}

interface UsersListResp { users: UserRow[] }
interface RateRequestsResp { requests: RateLimitRequest[] }

const KIND_LABEL: Record<LedgerEntry["kind"], string> = {
  stripe_purchase: "Stripe purchase",
  admin_credit: "Admin grant",
  correction_reward: "Correction reward",
  report_hold: "Report hold",
  report_commit: "Report charge",
  report_refund: "Report refund",
};

export default function AdminUsers() {
  useDocumentTitle("Users · Admin · CPD");

  const [search, setSearch] = useState("");
  const [listPath, setListPath] = useState<string>("/users?limit=20");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const usersState = useAdminFetch<UsersListResp>(listPath);

  // Reload the detail whenever selectedId changes or we trigger a
  // manual refresh (after granting credits etc.).
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const res = await adminFetch<UserDetail>(`/users/${id}`);
      setDetail(res);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Load failed.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else setDetail(null);
  }, [selectedId, loadDetail]);

  const onSearch = useCallback((e: FormEvent) => {
    e.preventDefault();
    const q = search.trim();
    setListPath(q ? `/users?q=${encodeURIComponent(q)}&limit=50` : "/users?limit=20");
  }, [search]);

  // ── Grant credits form ─────────────────────────────────────
  const [grantAmount, setGrantAmount] = useState("");
  const [grantReason, setGrantReason] = useState("");
  const [granting, setGranting] = useState(false);
  const [grantMsg, setGrantMsg] = useState<string | null>(null);
  const [grantErr, setGrantErr] = useState<string | null>(null);

  const onGrant = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedId) return;
    const amount = Number.parseInt(grantAmount, 10);
    if (!Number.isFinite(amount) || amount <= 0) {
      setGrantErr("Amount must be a positive integer.");
      return;
    }
    if (grantReason.trim().length < 3) {
      setGrantErr("Reason is required.");
      return;
    }
    setGranting(true);
    setGrantMsg(null);
    setGrantErr(null);
    try {
      await adminFetch(`/users/${selectedId}/grant-credits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount, reason: grantReason.trim() }),
      });
      setGrantMsg(`Granted ${amount} credits.`);
      setGrantAmount("");
      setGrantReason("");
      await loadDetail(selectedId);
    } catch (e) {
      setGrantErr(e instanceof Error ? e.message : "Grant failed.");
    } finally {
      setGranting(false);
    }
  }, [grantAmount, grantReason, selectedId, loadDetail]);

  // ── Rate-limit tier adjustment ─────────────────────────────
  const [tierSaving, setTierSaving] = useState(false);

  const onSetTier = useCallback(async (tier: RateLimitTier) => {
    if (!selectedId) return;
    setTierSaving(true);
    try {
      await adminFetch(`/users/${selectedId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rate_limit_tier: tier }),
      });
      await loadDetail(selectedId);
    } finally {
      setTierSaving(false);
    }
  }, [selectedId, loadDetail]);

  // ── Set plan (comp / free upgrade) ─────────────────────────
  const [planTarget, setPlanTarget] = useState<Plan | "">("");
  const [planReason, setPlanReason] = useState("");
  const [planSaving, setPlanSaving] = useState(false);
  const [planMsg, setPlanMsg] = useState<string | null>(null);
  const [planErr, setPlanErr] = useState<string | null>(null);

  // Re-seed the plan select when a new user is selected.
  useEffect(() => {
    setPlanTarget(detail?.user.current_plan ?? "");
    setPlanMsg(null);
    setPlanErr(null);
  }, [detail?.user.id, detail?.user.current_plan]);

  const onSetPlan = useCallback(async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedId || !planTarget) return;
    if (planReason.trim().length < 3) {
      setPlanErr("Reason is required.");
      return;
    }
    setPlanSaving(true);
    setPlanMsg(null);
    setPlanErr(null);
    try {
      const res = await adminFetch<{
        from_plan?: string;
        to_plan?: string;
        plan?: string;
        no_op?: boolean;
      }>(`/users/${selectedId}/set-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: planTarget, reason: planReason.trim() }),
      });
      if (res.no_op) {
        setPlanMsg(`Already on plan ${res.plan ?? planTarget}.`);
      } else {
        setPlanMsg(`Plan changed: ${res.from_plan} → ${res.to_plan}.`);
        setPlanReason("");
      }
      await loadDetail(selectedId);
    } catch (e) {
      setPlanErr(e instanceof Error ? e.message : "Plan change failed.");
    } finally {
      setPlanSaving(false);
    }
  }, [selectedId, planTarget, planReason, loadDetail]);

  // ── Rate-limit request queue ───────────────────────────────
  const requestsState = useAdminFetch<RateRequestsResp>("/rate-limit-requests?status=pending&limit=20");

  const [resolvingReqId, setResolvingReqId] = useState<string | null>(null);
  const onResolveRequest = useCallback(async (
    reqId: string,
    decision: "approved" | "denied",
    response: string,
    applyTier?: "extended" | "unlimited"
  ) => {
    setResolvingReqId(reqId);
    try {
      const body: Record<string, unknown> = {
        status: decision,
        admin_response: response,
      };
      if (decision === "approved" && applyTier) body.apply_tier = applyTier;
      await adminFetch(`/rate-limit-requests/${reqId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      requestsState.refresh();
    } finally {
      setResolvingReqId(null);
    }
  }, [requestsState]);

  return (
    <div className="admin__body">
      <div className="admin__panel">
        <h3>Users</h3>

        <form onSubmit={onSearch} className="admin__search">
          <input
            type="search"
            placeholder="Search by email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit">Search</button>
        </form>

        {usersState.error && (
          <p className="admin__error" role="alert">{usersState.error.message}</p>
        )}

        <table className="admin__table">
          <thead>
            <tr>
              <th>Email</th>
              <th>Plan</th>
              <th>Rate-limit</th>
              <th>Admin?</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(usersState.data?.users ?? []).map((u) => (
              <tr key={u.id} className={selectedId === u.id ? "admin__row--selected" : ""}>
                <td>{u.email}</td>
                <td>
                  {u.current_plan}
                  {u.plan_status !== "active" && u.plan_status !== "inactive" && (
                    <span style={{ opacity: 0.6 }}> ({u.plan_status})</span>
                  )}
                </td>
                <td>{u.rate_limit_tier}</td>
                <td>{u.is_admin ? "yes" : ""}</td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td>
                  <button type="button" onClick={() => setSelectedId(u.id)}>
                    {selectedId === u.id ? "Selected" : "Open"}
                  </button>
                </td>
              </tr>
            ))}
            {!usersState.loading && (usersState.data?.users ?? []).length === 0 && (
              <tr><td colSpan={6}>No matches.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selectedId && (
        <div className="admin__panel">
          <h3>User detail</h3>
          {detailLoading && <p>Loading…</p>}
          {detailError && <p className="admin__error" role="alert">{detailError}</p>}
          {detail && (
            <>
              <dl className="admin__meta">
                <dt>Email</dt><dd>{detail.user.email}</dd>
                <dt>Balance</dt>
                <dd><strong>{detail.balance}</strong> credits</dd>
                <dt>Rate-limit tier</dt>
                <dd>
                  <select
                    value={detail.user.rate_limit_tier}
                    onChange={(e) => void onSetTier(e.target.value as RateLimitTier)}
                    disabled={tierSaving}
                  >
                    <option value="default">default</option>
                    <option value="extended">extended</option>
                    <option value="unlimited">unlimited</option>
                    <option value="suspended">suspended</option>
                  </select>
                </dd>
                <dt>Plan</dt>
                <dd>
                  <strong>{detail.user.current_plan}</strong>
                  {" · "}
                  <span>{detail.user.plan_status}</span>
                  {detail.user.cancel_at_period_end && detail.user.plan_renews_at && (
                    <span style={{ opacity: 0.7 }}>
                      {" "}(cancels at {new Date(detail.user.plan_renews_at).toLocaleDateString()})
                    </span>
                  )}
                  {detail.user.stripe_subscription_id && (
                    <div style={{ opacity: 0.6, fontSize: "0.85em" }}>
                      sub: <code>{detail.user.stripe_subscription_id}</code>
                    </div>
                  )}
                </dd>
                {detail.user.plan_updated_at && (
                  <>
                    <dt>Plan updated</dt>
                    <dd>{new Date(detail.user.plan_updated_at).toLocaleString()}</dd>
                  </>
                )}
                <dt>Stripe customer</dt>
                <dd>{detail.user.stripe_customer_id ?? "—"}</dd>
                <dt>Last login</dt>
                <dd>
                  {detail.user.last_login_at
                    ? new Date(detail.user.last_login_at).toLocaleString()
                    : "—"}
                </dd>
                <dt>Account created</dt>
                <dd>{new Date(detail.user.created_at).toLocaleString()}</dd>
              </dl>

              <h4>Set plan (comp / free upgrade)</h4>
              <p style={{ opacity: 0.7, fontSize: "0.9em", marginTop: 0 }}>
                Flips <code>current_plan</code> + every non-revoked API key&apos;s tier.
                Blocked when the user has an active Stripe subscription.
              </p>
              <form onSubmit={onSetPlan} className="admin__form">
                <label>
                  <span>Plan</span>
                  <select
                    value={planTarget}
                    onChange={(e) => setPlanTarget(e.target.value as Plan)}
                    disabled={planSaving}
                  >
                    <option value="free">free</option>
                    <option value="dev">dev ($20/mo equivalent)</option>
                    <option value="pro">pro ($200/mo equivalent)</option>
                  </select>
                </label>
                <label>
                  <span>Reason (audit trail)</span>
                  <textarea
                    value={planReason}
                    onChange={(e) => setPlanReason(e.target.value)}
                    minLength={3}
                    maxLength={500}
                    rows={2}
                    placeholder="e.g. Journalist comp — election coverage"
                    required
                  />
                </label>
                {planErr && <p className="admin__error" role="alert">{planErr}</p>}
                {planMsg && <p className="admin__ok" role="status">{planMsg}</p>}
                <button
                  type="submit"
                  disabled={planSaving || planTarget === detail.user.current_plan}
                >
                  {planSaving
                    ? "Saving…"
                    : planTarget === detail.user.current_plan
                      ? `Already on ${detail.user.current_plan}`
                      : `Set plan to ${planTarget}`}
                </button>
              </form>

              <h4>Grant credits (comp)</h4>
              <form onSubmit={onGrant} className="admin__form">
                <label>
                  <span>Amount (credits)</span>
                  <input
                    type="number"
                    min={1}
                    max={100000}
                    value={grantAmount}
                    onChange={(e) => setGrantAmount(e.target.value)}
                    required
                  />
                </label>
                <label>
                  <span>Reason (audit trail)</span>
                  <textarea
                    value={grantReason}
                    onChange={(e) => setGrantReason(e.target.value)}
                    minLength={3}
                    maxLength={500}
                    rows={2}
                    placeholder="e.g. Journalist comp — election coverage"
                    required
                  />
                </label>
                {grantErr && <p className="admin__error" role="alert">{grantErr}</p>}
                {grantMsg && <p className="admin__ok" role="status">{grantMsg}</p>}
                <button type="submit" disabled={granting}>
                  {granting ? "Granting…" : "Grant credits"}
                </button>
              </form>

              <h4>Ledger history</h4>
              {detail.ledger.length === 0 ? (
                <p>No ledger entries.</p>
              ) : (
                <table className="admin__table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Kind</th>
                      <th>State</th>
                      <th style={{ textAlign: "right" }}>Δ</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.ledger.map((row) => (
                      <tr key={row.id}>
                        <td>{new Date(row.created_at).toLocaleString()}</td>
                        <td>{KIND_LABEL[row.kind]}</td>
                        <td>{row.state}</td>
                        <td style={{ textAlign: "right" }}>
                          {row.delta > 0 ? "+" : ""}{row.delta}
                        </td>
                        <td>{row.reason ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {detail.subscription_events.length > 0 && (
                <>
                  <h4>Recent subscription events</h4>
                  <table className="admin__table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Event</th>
                        <th>From → To</th>
                        <th>Source</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.subscription_events.map((ev) => {
                        const meta = (ev.metadata ?? {}) as Record<string, unknown>;
                        const source = typeof meta.source === "string"
                          ? meta.source
                          : "stripe";
                        const reason = typeof meta.reason === "string"
                          ? meta.reason
                          : (typeof meta.granted_by_email === "string"
                              ? String(meta.granted_by_email)
                              : "");
                        return (
                          <tr key={ev.id}>
                            <td>{new Date(ev.created_at).toLocaleString()}</td>
                            <td>{ev.event_type}</td>
                            <td>
                              {ev.from_plan ?? "—"} → {ev.to_plan ?? "—"}
                            </td>
                            <td>{source}</td>
                            <td>{reason}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )}
        </div>
      )}

      <div className="admin__panel">
        <h3>Pending rate-limit increase requests</h3>
        {requestsState.error && (
          <p className="admin__error" role="alert">{requestsState.error.message}</p>
        )}
        {(requestsState.data?.requests ?? []).length === 0 ? (
          <p>No pending requests.</p>
        ) : (
          <ul className="admin__list">
            {(requestsState.data?.requests ?? []).map((r) => (
              <RateLimitRequestItem
                key={r.id}
                request={r}
                disabled={resolvingReqId === r.id}
                onResolve={(decision, response, applyTier) =>
                  onResolveRequest(r.id, decision, response, applyTier)
                }
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function RateLimitRequestItem({
  request,
  disabled,
  onResolve,
}: {
  request: RateLimitRequest;
  disabled: boolean;
  onResolve: (
    decision: "approved" | "denied",
    response: string,
    applyTier?: "extended" | "unlimited"
  ) => Promise<void>;
}) {
  const [response, setResponse] = useState("");
  return (
    <li className="admin__list-item">
      <div>
        <strong>{request.email}</strong> asked for <code>{request.requested_tier}</code>
        {" · "}
        <time>{new Date(request.created_at).toLocaleString()}</time>
      </div>
      <p style={{ whiteSpace: "pre-wrap" }}>{request.reason}</p>
      <label>
        <span>Response</span>
        <textarea
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="Shown to the user"
        />
      </label>
      <div className="admin__actions">
        <button
          type="button"
          disabled={disabled || response.trim().length < 1}
          onClick={() => void onResolve("approved", response.trim(), request.requested_tier)}
        >
          Approve + apply {request.requested_tier}
        </button>
        <button
          type="button"
          disabled={disabled || response.trim().length < 1}
          onClick={() => void onResolve("denied", response.trim())}
        >
          Deny
        </button>
      </div>
    </li>
  );
}
