import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { userFetch } from "../api";
import { useUserAuth } from "../hooks/useUserAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

interface ApiKey {
  id: string;
  user_id: string;
  prefix: string;
  name: string;
  tier: "free" | "dev" | "pro";
  scopes: string[];
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  rotated_from_id: string | null;
  grace_until: string | null;
}

interface CreatedKey extends ApiKey {
  /** Full token, returned ONCE on create / rotate. */
  token: string;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function statusOf(k: ApiKey): { label: string; cls: string } {
  if (k.revoked_at) return { label: "revoked", cls: "cpd-auth__chip--muted" };
  if (k.expires_at && new Date(k.expires_at).getTime() < Date.now()) {
    return { label: "expired", cls: "cpd-auth__chip--muted" };
  }
  if (k.grace_until && new Date(k.grace_until).getTime() > Date.now()) {
    return { label: "rotating (grace)", cls: "cpd-auth__chip--warn" };
  }
  return { label: "active", cls: "cpd-auth__chip--ok" };
}

/**
 * /account/api-keys — self-service CRUD over the developer API keys
 * the user owns. Backed by /api/v1/me/api-keys (services/api/src/routes/keys.ts).
 *
 * Full tokens are surfaced ONCE on create / rotate via a banner the user
 * must explicitly dismiss; the list view never re-shows them. Token
 * storage on the server is HMAC-hashed — it's literally not retrievable
 * after creation.
 */
export default function ApiKeysPage() {
  useDocumentTitle("API keys · Canadian Political Data");
  const { user, loading: authLoading, disabled } = useUserAuth();
  const [items, setItems] = useState<ApiKey[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Inline "create" form state.
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createExpiresDays, setCreateExpiresDays] = useState<string>("");
  const [creating, setCreating] = useState(false);

  // The single most-recently-shown full token. Persists in component
  // state (NOT in DB / localStorage) until the user explicitly acks.
  const [showToken, setShowToken] = useState<CreatedKey | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await userFetch<{ api_keys: ApiKey[] }>("/me/api-keys");
      setItems(res.api_keys);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (user) void load();
  }, [user, load]);

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
        <h2>Sign in to manage API keys</h2>
        <p><Link to="/login?from=/account/api-keys">Sign in →</Link></p>
      </section>
    );
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { name: createName.trim() };
      const days = createExpiresDays.trim();
      if (days) body.expires_in_days = Number(days);
      const created = await userFetch<CreatedKey>("/me/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setShowToken(created);
      setCreateOpen(false);
      setCreateName("");
      setCreateExpiresDays("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed.");
    } finally {
      setCreating(false);
    }
  }

  async function onRotate(k: ApiKey) {
    if (!confirm(
      `Rotate "${k.name}"? The current token will continue to work for 24h, ` +
      `then stop. Make sure you can swap to the new token within that window.`
    )) return;
    setBusyId(k.id);
    setError(null);
    try {
      const created = await userFetch<CreatedKey>(`/me/api-keys/${k.id}/rotate`, {
        method: "POST",
      });
      setShowToken(created);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rotate failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function onRevoke(k: ApiKey) {
    if (!confirm(
      `Revoke "${k.name}"? The token will stop working immediately. ` +
      `This cannot be undone.`
    )) return;
    setBusyId(k.id);
    setError(null);
    try {
      await userFetch<void>(`/me/api-keys/${k.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revoke failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function onCopyToken() {
    if (!showToken) return;
    try {
      await navigator.clipboard.writeText(showToken.token);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable — user can still select + copy by hand.
    }
  }

  const list = items ?? [];

  return (
    <section className="cpd-auth">
      <h2>Developer API keys</h2>
      <p className="cpd-auth__sub">
        Tokens for the <code>/api/public/v1/*</code> surface. Each key is
        identified by a short prefix; the full token is shown only once
        when you create or rotate it. Storage is one-way hashed — we
        cannot recover a token after this page closes.
      </p>

      {error && <p className="cpd-auth__error" role="alert">{error}</p>}

      {showToken && (
        <div className="cpd-auth__notice cpd-auth__notice--warn" role="alert">
          <h3>Your new token — copy it now</h3>
          <p>
            This is the <strong>only time</strong> you'll see <code>{showToken.name}</code>'s
            full token. Store it somewhere safe (a secrets manager, a CI variable,
            or your password manager). After you dismiss this banner, it can't be
            shown again — you'll need to rotate the key to get a new one.
          </p>
          <pre className="cpd-auth__token-box"><code>{showToken.token}</code></pre>
          <div className="cpd-auth__row">
            <button type="button" onClick={onCopyToken}>
              {copied ? "Copied ✓" : "Copy token"}
            </button>
            <button
              type="button"
              className="cpd-auth__signout"
              onClick={() => setShowToken(null)}
            >
              I've saved it — dismiss
            </button>
          </div>
        </div>
      )}

      <div className="cpd-auth__row" style={{ marginTop: "1.5rem" }}>
        {!createOpen && (
          <button type="button" onClick={() => setCreateOpen(true)}>
            + New API key
          </button>
        )}
      </div>

      {createOpen && (
        <form onSubmit={onCreate} className="cpd-auth__form" style={{ marginTop: "1rem" }}>
          <label>
            Name
            <input
              type="text"
              required
              maxLength={100}
              value={createName}
              onChange={e => setCreateName(e.target.value)}
              placeholder="e.g. production worker"
              autoFocus
            />
          </label>
          <label>
            Expires in (days, optional)
            <input
              type="number"
              min={1}
              max={3650}
              value={createExpiresDays}
              onChange={e => setCreateExpiresDays(e.target.value)}
              placeholder="leave blank for no expiry"
            />
          </label>
          <div className="cpd-auth__row">
            <button type="submit" disabled={creating || !createName.trim()}>
              {creating ? "Creating…" : "Create key"}
            </button>
            <button
              type="button"
              className="cpd-auth__signout"
              onClick={() => { setCreateOpen(false); setCreateName(""); setCreateExpiresDays(""); }}
              disabled={creating}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading && !items && <p>Loading keys…</p>}

      {!loading && list.length === 0 && (
        <p className="cpd-auth__sub" style={{ marginTop: "1.5rem" }}>
          No API keys yet. Create one above to start calling{" "}
          <code>/api/public/v1/*</code> with{" "}
          <code>Authorization: Bearer cpd_…</code>.
        </p>
      )}

      {list.length > 0 && (
        <table className="cpd-auth__table" style={{ marginTop: "1.5rem" }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Prefix</th>
              <th>Tier</th>
              <th>Status</th>
              <th>Last used</th>
              <th>Created</th>
              <th>Expires</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.map(k => {
              const status = statusOf(k);
              const isLive = !k.revoked_at;
              return (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td><code>{k.prefix}</code></td>
                  <td>{k.tier}</td>
                  <td>
                    <span className={`cpd-auth__chip ${status.cls}`}>
                      {status.label}
                    </span>
                  </td>
                  <td>{fmtDate(k.last_used_at)}</td>
                  <td>{fmtDate(k.created_at)}</td>
                  <td>{fmtDate(k.expires_at)}</td>
                  <td>
                    {isLive && (
                      <>
                        <button
                          type="button"
                          disabled={busyId === k.id}
                          onClick={() => onRotate(k)}
                        >
                          Rotate
                        </button>
                        {" "}
                        <button
                          type="button"
                          className="cpd-auth__signout"
                          disabled={busyId === k.id}
                          onClick={() => onRevoke(k)}
                        >
                          Revoke
                        </button>
                      </>
                    )}
                    {k.revoked_at && (
                      <span className="cpd-auth__sub">
                        revoked {fmtDate(k.revoked_at)}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
