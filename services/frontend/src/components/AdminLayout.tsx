import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useUserAuth } from "../hooks/useUserAuth";
import { useAdminFetch } from "../hooks/useAdminFetch";
import "../styles/admin.css";

interface CorrectionsStats {
  pending: number;
  triaged: number;
  applied: number;
  rejected: number;
  duplicate: number;
  spam: number;
}

/**
 * Admin shell. Access = "signed-in user with is_admin=true". Unauthed
 * visitors are bounced to the shared /login page; signed-in non-admins
 * see a small 403 surface (not a redirect — the user has an account,
 * they just lack the role, so redirecting to /login is confusing).
 */
export function AdminLayout() {
  const { user, loading, logout } = useUserAuth();
  const loc = useLocation();
  // Surface a pending-corrections badge in the nav so the admin notices
  // new submissions without clicking through. Polls only when signed in
  // as an admin (the path is null until that's true).
  const correctionsStats = useAdminFetch<CorrectionsStats>(
    user?.is_admin ? "/corrections/stats" : null,
    { pollMs: 30000 },
  );
  const pendingCorrections = correctionsStats.data?.pending ?? 0;

  if (loading) {
    return <section className="admin admin--login"><p>Checking session…</p></section>;
  }

  if (!user) {
    const from = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/login?from=${from}`} replace />;
  }

  if (!user.is_admin) {
    return (
      <section className="admin admin--login">
        <header className="admin__header">
          <div className="admin__brand">
            <span aria-hidden="true">⚙️</span>
            <h2>Admin</h2>
          </div>
        </header>
        <p>Your account ({user.email}) does not have admin access.</p>
        <p>
          <button className="admin__logout" onClick={() => logout()}>Sign out</button>
        </p>
      </section>
    );
  }

  return (
    <section className="admin">
      <header className="admin__header">
        <div className="admin__brand">
          <span aria-hidden="true">⚙️</span>
          <h2>Admin</h2>
          <span className="admin__who">{user.email}</span>
        </div>
        <nav className="admin__subnav" aria-label="Admin">
          <NavLink to="/admin" end className={({ isActive }) => (isActive ? "active" : "")}>
            Dashboard
          </NavLink>
          <NavLink to="/admin/jobs" className={({ isActive }) => (isActive ? "active" : "")}>
            Jobs
          </NavLink>
          <NavLink to="/admin/schedules" className={({ isActive }) => (isActive ? "active" : "")}>
            Schedules
          </NavLink>
          <NavLink to="/admin/socials" className={({ isActive }) => (isActive ? "active" : "")}>
            Socials
          </NavLink>
          <NavLink to="/admin/corrections" className={({ isActive }) => (isActive ? "active" : "")}>
            Corrections
            {pendingCorrections > 0 && (
              <span
                className="admin__nav-badge"
                aria-label={`${pendingCorrections} pending corrections`}
                title={`${pendingCorrections} pending`}
              >
                {pendingCorrections > 99 ? "99+" : pendingCorrections}
              </span>
            )}
          </NavLink>
          <NavLink to="/admin/users" className={({ isActive }) => (isActive ? "active" : "")}>
            Users
          </NavLink>
          <NavLink to="/admin/reports" className={({ isActive }) => (isActive ? "active" : "")}>
            Reports
          </NavLink>
          <NavLink to="/admin/usage" className={({ isActive }) => (isActive ? "active" : "")}>
            Usage
          </NavLink>
          <button className="admin__logout" onClick={() => logout()}>Sign out</button>
        </nav>
      </header>
      <Outlet />
    </section>
  );
}
