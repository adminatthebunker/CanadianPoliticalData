import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  itemsOf,
  usePoliticianSocials,
  type PoliticianCore,
  type PoliticianSocial,
} from "../hooks/usePolitician";
import { SocialIcon, platformLabel } from "./SocialIcon";
import { useUserAuth } from "../hooks/useUserAuth";

/**
 * Combined "Socials & posts" tab on the politician profile.
 *
 * Two sections, top to bottom:
 *
 *   1. **Handles** — the politician's known social accounts (one card
 *      per platform with liveness badge + follower count). Sourced
 *      from the normalised /api/v1/socials/politicians/:id route with
 *      a JSONB fallback when that route isn't deployed yet.
 *
 *   2. **Recent posts** — scraped content captured by paying
 *      subscribers, with attribution opt-in surfacing as "Funded by
 *      …". Public-read since v2 (governance docs shipped 2026-05-12).
 *      An inline CTA banner routes signed-in users to the Monitor
 *      panel and anonymous visitors to /login.
 *
 * Pre-v4 the two sections lived in separate tabs (PoliticianSocialsTab
 * + PoliticianPostsTab); they were merged 2026-05-12 because they
 * naturally answer the same question — *what's this politician's
 * social-media footprint?*
 */
interface Props {
  politicianId: string;
  politician: PoliticianCore | null;
}

export function PoliticianSocialsTab({ politicianId, politician }: Props) {
  return (
    <div className="pol-tab">
      <HandlesSection politicianId={politicianId} politician={politician} />
      <PostsSection politicianId={politicianId} />
    </div>
  );
}

// ── Handles section ────────────────────────────────────────────────


/** Derive socials from the raw JSONB on the politician record — used
 *  as a fallback when the Phase 5 /api/v1/socials/politicians/:id
 *  route hasn't been deployed yet. */
function fallbackFromJson(p: PoliticianCore | null): PoliticianSocial[] {
  if (!p?.social_urls) return [];
  const out: PoliticianSocial[] = [];
  for (const [platform, url] of Object.entries(p.social_urls)) {
    if (!url || typeof url !== "string") continue;
    out.push({
      id: `jsonb:${platform}`,
      politician_id: p.id,
      platform,
      handle: null,
      url,
      last_verified_at: null,
      is_live: null,
      follower_count: null,
    });
  }
  return out;
}

function HandlesSection({ politicianId, politician }: Props) {
  const { data, loading, error, notFound } = usePoliticianSocials(politicianId);

  if (loading) {
    return <div className="pol-tab__loading">Loading social accounts…</div>;
  }

  const fromApi = itemsOf<PoliticianSocial>(data ?? null);
  const socials = fromApi.length ? fromApi : fallbackFromJson(politician);

  if (error && !socials.length) {
    return (
      <div className="pol-tab__error">
        Failed to load socials: {error.message}
      </div>
    );
  }

  if (!socials.length) {
    return (
      <section className="pol-tab__section">
        <h3 className="pol-tab__section-title">Handles</h3>
        <div className="pol-tab__empty">
          <strong>No social accounts on file.</strong>
          <p>
            {notFound
              ? "Social-handle tracking isn't available for this politician yet."
              : "Nothing has been discovered through Open North or the enrichment scrapers."}
          </p>
        </div>
      </section>
    );
  }

  const usingFallback = fromApi.length === 0 && socials.length > 0;

  return (
    <section className="pol-tab__section">
      <h3 className="pol-tab__section-title">Handles</h3>
      {usingFallback && (
        <p className="pol-tab__note">
          Showing raw handles from the Open North feed — liveness verification
          isn't wired up for this politician yet.
        </p>
      )}
      <div className="pol-socials__grid">
        {socials.map(s => <SocialCard key={s.id} social={s} />)}
      </div>
    </section>
  );
}

type SocialStatus = "live" | "dead" | "unknown" | "unverified";

function SocialCard({ social: s }: { social: PoliticianSocial }) {
  const label = platformLabel(s.platform);
  const handle = s.handle ?? deriveHandle(s.url, s.platform);
  const neverVerified = s.last_verified_at === null;
  const status: SocialStatus =
    neverVerified ? "unverified"
    : s.is_live === true ? "live"
    : s.is_live === false ? "dead"
    : "unknown";

  return (
    <a
      className={`pol-social-card pol-social-card--${status}`}
      href={s.url}
      target="_blank"
      rel="noopener noreferrer"
    >
      <div className="pol-social-card__icon" aria-hidden="true">
        <SocialIcon platform={s.platform} size={20} />
      </div>
      <div className="pol-social-card__body">
        <div className="pol-social-card__platform">{label}</div>
        {handle && <div className="pol-social-card__handle">{handle}</div>}
        <div className="pol-social-card__url">{shortUrl(s.url)}</div>
      </div>
      <StatusBadge status={status} lastVerifiedAt={s.last_verified_at} />
    </a>
  );
}

function StatusBadge({
  status, lastVerifiedAt,
}: {
  status: SocialStatus;
  lastVerifiedAt: string | null;
}) {
  if (status === "unverified") {
    return (
      <span className="pol-social-card__badge pol-social-card__badge--unverified" title="Never verified">
        ?
      </span>
    );
  }
  if (status === "unknown") {
    const when = lastVerifiedAt ? new Date(lastVerifiedAt).toLocaleDateString() : null;
    return (
      <span
        className="pol-social-card__badge pol-social-card__badge--unknown"
        title={when ? `Couldn't verify on ${when} — try the link` : "Couldn't verify — try the link"}
      >
        ?
      </span>
    );
  }
  if (status === "dead") {
    return (
      <span
        className="pol-social-card__badge pol-social-card__badge--dead"
        title={lastVerifiedAt ? `Dead as of ${new Date(lastVerifiedAt).toLocaleDateString()}` : "Dead"}
      >
        dead
      </span>
    );
  }
  return (
    <span
      className="pol-social-card__badge pol-social-card__badge--live"
      title={lastVerifiedAt ? `Last verified ${new Date(lastVerifiedAt).toLocaleDateString()}` : "Live"}
    >
      live
    </span>
  );
}

function deriveHandle(url: string, platform: string): string | null {
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    if (!parts.length) return null;
    const first = parts[0].replace(/^@/, "");
    return platform.toLowerCase() === "tiktok" ? `@${first}` : `@${first}`;
  } catch {
    return null;
  }
}

function shortUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.hostname}${u.pathname === "/" ? "" : u.pathname}`.replace(/\/$/, "");
  } catch {
    return url;
  }
}

// ── Posts section ──────────────────────────────────────────────────


interface ScrapedPost {
  id: string;
  politician_id: string;
  platform: string;
  post_id: string;
  posted_at: string | null;
  text: string;
  url: string | null;
  media_urls: string[] | null;
  engagement: Record<string, number> | null;
  scraped_at: string;
  funded_by: string | null;
  funded_by_url: string | null;
}

const PLATFORM_LABEL: Record<string, string> = {
  twitter: "Twitter / X",
  bluesky: "Bluesky",
  instagram: "Instagram",
  mastodon: "Mastodon",
};

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime();
  const diff = (Date.now() - ms) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  if (diff < 86400 * 30) return `${Math.round(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function PlatformPill({ platform }: { platform: string }) {
  const label = PLATFORM_LABEL[platform] ?? platform;
  return <span className={`pol-posts__pill pol-posts__pill--${platform}`}>{label}</span>;
}

// ── Dedup (v7b-3) ──────────────────────────────────────────────────
// Politicians routinely cross-post the same content to Twitter, Bluesky,
// Instagram, and Mastodon within minutes. Render one card per logical
// post with all platforms shown as pills, instead of N near-identical
// cards spamming the list. Frontend-only — the underlying social_posts
// rows stay distinct in the DB (each platform's post_id is canonical).

const DEDUP_WINDOW_MS = 15 * 60 * 1000;
const DEDUP_MIN_TEXT_LEN = 20;

function normalizePostText(t: string | null | undefined): string {
  if (!t) return "";
  return t
    .toLowerCase()
    .replace(/https?:\/\/\S+/g, "")  // urls (UTM differs across platforms)
    .replace(/@[\w.\-]+/g, "")       // @-handles (formats differ per platform)
    .replace(/\s+/g, " ")            // collapse whitespace
    .trim();
}

interface PostGroup {
  leader: ScrapedPost;
  members: ScrapedPost[];   // includes leader, sorted newest-first
  platforms: string[];      // unique, in first-seen order
}

function groupPostsByContent(posts: ScrapedPost[]): PostGroup[] {
  // Newest-first so the most recent variant of a cross-post is the
  // group leader (text + date come from this row).
  const sorted = [...posts].sort((a, b) => {
    const ta = a.posted_at ? new Date(a.posted_at).getTime() : 0;
    const tb = b.posted_at ? new Date(b.posted_at).getTime() : 0;
    return tb - ta;
  });
  const groups: PostGroup[] = [];
  for (const p of sorted) {
    const norm = normalizePostText(p.text);
    // Short / empty posts are too prone to false-positive matches
    // ("Yes." "Thanks!" "RT"). Don't dedup them.
    if (norm.length < DEDUP_MIN_TEXT_LEN) {
      groups.push({ leader: p, members: [p], platforms: [p.platform] });
      continue;
    }
    const pTime = p.posted_at ? new Date(p.posted_at).getTime() : null;
    let matched: PostGroup | null = null;
    for (const g of groups) {
      if (normalizePostText(g.leader.text) !== norm) continue;
      if (pTime !== null && g.leader.posted_at) {
        const gTime = new Date(g.leader.posted_at).getTime();
        if (Math.abs(gTime - pTime) > DEDUP_WINDOW_MS) continue;
      }
      matched = g;
      break;
    }
    if (matched) {
      matched.members.push(p);
      if (!matched.platforms.includes(p.platform)) {
        matched.platforms.push(p.platform);
      }
    } else {
      groups.push({ leader: p, members: [p], platforms: [p.platform] });
    }
  }
  return groups;
}

function EngagementLine({ engagement }: { engagement: Record<string, number> | null }) {
  if (!engagement) return null;
  const parts: string[] = [];
  if (engagement.likes != null) parts.push(`${engagement.likes.toLocaleString()} ♥`);
  if (engagement.reposts != null) parts.push(`${engagement.reposts.toLocaleString()} ↻`);
  if (engagement.replies != null) parts.push(`${engagement.replies.toLocaleString()} 💬`);
  if (engagement.views != null) parts.push(`${engagement.views.toLocaleString()} views`);
  if (parts.length === 0) return null;
  return <span className="pol-posts__engagement">{parts.join(" · ")}</span>;
}

function PostsSection({ politicianId }: { politicianId: string }) {
  const { user, loading: authLoading } = useUserAuth();
  const location = useLocation();
  const [posts, setPosts] = useState<ScrapedPost[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // CTA targets: signed-in → monitor flow on the same page (#monitor
  // hash triggers MonitorPoliticianButton to auto-open). Anonymous →
  // /login with a return URL back to this politician's profile
  // #socials tab (the new combined-tab anchor).
  const signedInCtaHref = `${location.pathname}#monitor`;
  const anonReturn = encodeURIComponent(location.pathname + "#socials");
  const anonCtaHref = `/login?from=${anonReturn}`;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/api/v1/socials/politicians/${politicianId}/posts?limit=50`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(d => {
        if (cancelled) return;
        setPosts(d.items ?? []);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [politicianId]);

  // Always render the section header so users see the structure even
  // when there are no posts (or while loading) — it grounds the
  // empty-state CTA.
  return (
    <section className="pol-tab__section">
      <h3 className="pol-tab__section-title">Recent posts</h3>
      <PostsSectionBody
        posts={posts}
        loading={loading}
        error={error}
        signedInCtaHref={signedInCtaHref}
        anonCtaHref={anonCtaHref}
        authLoading={authLoading}
        isSignedIn={!!user}
      />
    </section>
  );
}

function PostsSectionBody({
  posts,
  loading,
  error,
  signedInCtaHref,
  anonCtaHref,
  authLoading,
  isSignedIn,
}: {
  posts: ScrapedPost[] | null;
  loading: boolean;
  error: string | null;
  signedInCtaHref: string;
  anonCtaHref: string;
  authLoading: boolean;
  isSignedIn: boolean;
}) {
  if (loading) return <div className="pol-tab__loading">Loading recent posts…</div>;
  if (error) return <div className="pol-tab__error">Failed to load posts: {error}</div>;

  if (!posts || posts.length === 0) {
    return (
      <div className="pol-tab__empty">
        <p>No scraped social-media posts captured for this politician yet.</p>
        {!authLoading && isSignedIn ? (
          <p>
            <Link to={signedInCtaHref} className="pol-posts__cta-primary">
              Set up monitoring →
            </Link>{" "}
            <span className="pol-tab__hint">
              Pull recent posts from this politician's public accounts on a schedule.{" "}
              <Link to="/about/monitoring/">Learn how it works</Link>.
            </span>
          </p>
        ) : (
          <p>
            <Link to={anonCtaHref} className="pol-posts__cta-primary">
              Sign in to fund the first monitoring →
            </Link>{" "}
            <span className="pol-tab__hint">
              Free to read; paid monitoring debits credits per refresh.{" "}
              <Link to="/about/monitoring/">Learn how it works</Link>.
            </span>
          </p>
        )}
        <p className="pol-tab__hint">
          See the <Link to="/about/disclaimer/">disclaimer</Link> for what gets captured
          and the <Link to="/about/takedown/">takedown policy</Link> for removal requests.
        </p>
      </div>
    );
  }

  return (
    <div className="pol-posts">
      <div className="pol-posts__cta">
        <span className="pol-posts__cta-lede">
          These posts come from paid social-media monitoring.
        </span>{" "}
        {!authLoading && isSignedIn ? (
          <Link to={signedInCtaHref} className="pol-posts__cta-primary">
            Set up your own monitoring →
          </Link>
        ) : (
          <Link to={anonCtaHref} className="pol-posts__cta-primary">
            Sign in to fund your own monitoring →
          </Link>
        )}{" "}
        <Link to="/about/monitoring/" className="pol-posts__cta-secondary">
          Learn more
        </Link>
      </div>
      <ul className="pol-posts__list">
        {groupPostsByContent(posts).map(g => {
          const p = g.leader;
          const copies = g.members.length;
          // Prefer the leader's URL; surface per-platform "source"
          // links for the remaining members so visitors can verify
          // each cross-post independently.
          const extraSources = g.members
            .filter(m => m.platform !== p.platform && m.url)
            .map(m => ({ platform: m.platform, url: m.url! }));
          // Attribution: any member's funded_by takes precedence over
          // anonymous; pick the first non-null. (In practice all
          // members share a subscription owner, but the user could
          // theoretically fund the same politician on multiple
          // platforms via separate handles — the first attributed one
          // wins, keeping the line short.)
          const attributedMember = g.members.find(m => m.funded_by) ?? p;
          return (
            <li key={`${p.platform}:${p.post_id}`} className="pol-posts__row">
              <div className="pol-posts__row-head">
                {g.platforms.map(pl => <PlatformPill key={pl} platform={pl} />)}
                {copies > 1 && (
                  <span
                    className="pol-posts__copies"
                    title={`Cross-posted to ${g.platforms.length} platforms`}
                  >
                    +{copies - 1} {copies === 2 ? "copy" : "copies"}
                  </span>
                )}
                <span className="pol-posts__date">{formatRelative(p.posted_at)}</span>
                {p.url && (
                  <a className="pol-posts__src" href={p.url} target="_blank" rel="noopener noreferrer">
                    source ↗
                  </a>
                )}
              </div>
              {p.text && <p className="pol-posts__text">{p.text}</p>}
              {extraSources.length > 0 && (
                <div className="pol-posts__alt-sources">
                  {extraSources.map(s => (
                    <a
                      key={s.platform}
                      className="pol-posts__alt-source"
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      on {PLATFORM_LABEL[s.platform] ?? s.platform} ↗
                    </a>
                  ))}
                </div>
              )}
              <div className="pol-posts__row-meta">
                <EngagementLine engagement={p.engagement} />
                {attributedMember.funded_by ? (
                  <span className="pol-posts__attribution">
                    Funded by{" "}
                    {attributedMember.funded_by_url ? (
                      <a
                        href={attributedMember.funded_by_url}
                        target="_blank"
                        rel="nofollow noopener external"
                        className="pol-posts__handle pol-posts__handle--link"
                      >
                        {attributedMember.funded_by}
                      </a>
                    ) : (
                      <span className="pol-posts__handle">{attributedMember.funded_by}</span>
                    )}
                  </span>
                ) : (
                  <span className="pol-posts__attribution pol-posts__attribution--anon">
                    Scraped via paid monitoring
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
