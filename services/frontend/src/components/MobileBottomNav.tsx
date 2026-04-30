import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useUserAuth } from "../hooks/useUserAuth";

/**
 * Phone-only bottom navigation. Pinned to the bottom of the viewport on
 * <= 640px viewports. Four primary destinations + a "More" tab that opens a
 * sheet for secondary nav (Coverage, Blog, Share, Contact). The top header
 * keeps brand + auth indicator only on phones — see Layout.tsx.
 */

const PRIMARY: Array<{ to: string; label: string; icon: string; end?: boolean }> = [
  { to: "/", label: "Home", icon: "🍁", end: true },
  { to: "/map", label: "Map", icon: "🗺" },
  { to: "/politicians", label: "Politicians", icon: "👥" },
  { to: "/search", label: "Search", icon: "🔎" },
];

interface MoreSheetProps {
  open: boolean;
  onClose: () => void;
}

function MoreSheet({ open, onClose }: MoreSheetProps) {
  const { user } = useUserAuth();
  const sheetRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function shareCurrentPage() {
    const url = window.location.href;
    const title = document.title;
    const nav = typeof navigator !== "undefined" ? navigator : null;
    if (nav && typeof nav.share === "function") {
      try {
        await nav.share({ title, url });
        onClose();
        return;
      } catch {
        /* user cancelled — fall through to clipboard */
      }
    }
    if (nav && nav.clipboard) {
      try {
        await nav.clipboard.writeText(url);
      } catch {
        /* clipboard unavailable */
      }
    }
    onClose();
  }

  return (
    <div
      className="mobile-more-sheet__backdrop"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={sheetRef}
        className="mobile-more-sheet"
        role="dialog"
        aria-modal="true"
        aria-label="More navigation"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mobile-more-sheet__handle" aria-hidden="true" />
        <h2 className="mobile-more-sheet__title">More</h2>
        <div className="mobile-more-sheet__grid">
          <NavLink to="/semantic-map" className="mobile-more-sheet__item" onClick={onClose}>
            <span className="mobile-more-sheet__icon" aria-hidden="true">🌐</span>
            <span>Explore</span>
          </NavLink>
          <NavLink to="/coverage" className="mobile-more-sheet__item" onClick={onClose}>
            <span className="mobile-more-sheet__icon" aria-hidden="true">📊</span>
            <span>Coverage</span>
          </NavLink>
          <a
            href="https://docs.canadianpoliticaldata.org/blog/"
            className="mobile-more-sheet__item"
            target="_blank"
            rel="noopener noreferrer"
            onClick={onClose}
          >
            <span className="mobile-more-sheet__icon" aria-hidden="true">📝</span>
            <span>Blog</span>
          </a>
          <NavLink to="/corrections" className="mobile-more-sheet__item" onClick={onClose}>
            <span className="mobile-more-sheet__icon" aria-hidden="true">✏️</span>
            <span>Corrections</span>
          </NavLink>
          <button
            type="button"
            className="mobile-more-sheet__item"
            onClick={shareCurrentPage}
          >
            <span className="mobile-more-sheet__icon" aria-hidden="true">🔗</span>
            <span>Share page</span>
          </button>
          <a
            className="mobile-more-sheet__item"
            href="mailto:admin@thebunkerops.ca?subject=CanadianPoliticalData%20feedback"
            onClick={onClose}
          >
            <span className="mobile-more-sheet__icon" aria-hidden="true">✉️</span>
            <span>Contact</span>
          </a>
          {user ? (
            <NavLink to="/account" className="mobile-more-sheet__item" onClick={onClose}>
              <span className="mobile-more-sheet__icon" aria-hidden="true">👤</span>
              <span>Account</span>
            </NavLink>
          ) : (
            <NavLink to="/login" className="mobile-more-sheet__item" onClick={onClose}>
              <span className="mobile-more-sheet__icon" aria-hidden="true">🔑</span>
              <span>Sign in</span>
            </NavLink>
          )}
        </div>
        <button type="button" className="mobile-more-sheet__close" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

export function MobileBottomNav() {
  const [moreOpen, setMoreOpen] = useState(false);
  const location = useLocation();

  // Close the sheet whenever the user navigates so the next page isn't covered.
  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  return (
    <>
      <nav className="mobile-bottom-nav" aria-label="Primary mobile navigation">
        {PRIMARY.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              "mobile-bottom-nav__item" + (isActive ? " is-active" : "")
            }
          >
            <span className="mobile-bottom-nav__icon" aria-hidden="true">{item.icon}</span>
            <span className="mobile-bottom-nav__label">{item.label}</span>
          </NavLink>
        ))}
        <button
          type="button"
          className={"mobile-bottom-nav__item" + (moreOpen ? " is-active" : "")}
          onClick={() => setMoreOpen((v) => !v)}
          aria-expanded={moreOpen}
          aria-haspopup="dialog"
        >
          <span className="mobile-bottom-nav__icon" aria-hidden="true">⋯</span>
          <span className="mobile-bottom-nav__label">More</span>
        </button>
      </nav>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  );
}
