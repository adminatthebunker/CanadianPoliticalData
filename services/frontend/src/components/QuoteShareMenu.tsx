import { useEffect, useRef, useState } from "react";
import "../styles/quote-share.css";

// Reusable "share this quote" popover. Lifted out of SpeechResultCard so the
// search-result card and the speech-detail exchange rows render the same UI.
//
// Class names live under `.quote-share__*` (see styles/quote-share.css) — the
// previous `.speech-result__share*` block was renamed when the component was
// extracted, so the styles are no longer scoped to a single page.

interface ShareTarget {
  key: string;
  label: string;
  icon: string;
  href: (url: string, text: string) => string;
  newTab: boolean;
}

const SHARE_TARGETS: ShareTarget[] = [
  { key: "x",        label: "X / Twitter", icon: "𝕏", newTab: true,
    href: (u, x) => `https://twitter.com/intent/tweet?url=${encodeURIComponent(u)}&text=${encodeURIComponent(x)}` },
  { key: "bluesky",  label: "Bluesky", icon: "🦋", newTab: true,
    href: (u, x) => `https://bsky.app/intent/compose?text=${encodeURIComponent(`${x} ${u}`)}` },
  { key: "facebook", label: "Facebook", icon: "f", newTab: true,
    href: (u) => `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(u)}` },
  { key: "linkedin", label: "LinkedIn", icon: "in", newTab: true,
    href: (u) => `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(u)}` },
  { key: "reddit",   label: "Reddit", icon: "r/", newTab: true,
    href: (u, x) => `https://www.reddit.com/submit?url=${encodeURIComponent(u)}&title=${encodeURIComponent(x)}` },
  { key: "whatsapp", label: "WhatsApp", icon: "💬", newTab: true,
    href: (u, x) => `https://api.whatsapp.com/send?text=${encodeURIComponent(`${x} ${u}`)}` },
  { key: "email",    label: "Email", icon: "✉", newTab: false,
    href: (u, x) => `mailto:?subject=${encodeURIComponent("Quote from Canadian Political Data")}&body=${encodeURIComponent(`${x}\n\n${u}`)}` },
];

function buildShareText(speakerName: string, dateIso: string | null, quoteText: string): string {
  const date = dateIso
    ? new Date(dateIso).toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" })
    : "";
  // Cap at 220 chars to leave room for attribution + URL inside Twitter's 280 budget.
  const quote = quoteText.length > 220 ? `${quoteText.slice(0, 217)}…` : quoteText;
  const attribution = date ? `— ${speakerName}, ${date}` : `— ${speakerName}`;
  return `“${quote}” ${attribution}`;
}

export interface QuoteShareMenuProps {
  speakerName: string;
  dateIso: string | null;
  quoteText: string;
  /** Internal app URL for the speech, optionally with a `#chunk-<id>` anchor. */
  internalUrl: string;
  /** Optional ourcommons.ca embed URL (federal speeches only). */
  videoUrl?: string | null;
  /** Optional upstream Hansard URL. */
  hansardUrl?: string | null;
  /** Compact icon-only trigger for tight rows in the exchange view. */
  compact?: boolean;
}

export function QuoteShareMenu({
  speakerName,
  dateIso,
  quoteText,
  internalUrl,
  videoUrl,
  hansardUrl,
  compact = false,
}: QuoteShareMenuProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<"link" | "quote" | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const absoluteUrl = typeof window !== "undefined"
    ? new URL(internalUrl, window.location.origin).toString()
    : internalUrl;
  const shareText = buildShareText(speakerName, dateIso, quoteText);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleButton = async () => {
    if (typeof navigator !== "undefined" && navigator.share) {
      try {
        await navigator.share({ url: absoluteUrl, text: shareText, title: "Canadian Political Data" });
        return;
      } catch { /* user cancelled — fall through to dropdown */ }
    }
    setOpen((o) => !o);
  };

  const copy = async (what: "link" | "quote") => {
    try {
      await navigator.clipboard.writeText(what === "link" ? absoluteUrl : `${shareText}\n${absoluteUrl}`);
      setCopied(what);
      setTimeout(() => setCopied(null), 1600);
    } catch { /* noop */ }
  };

  return (
    <div className="quote-share" ref={ref}>
      <button
        type="button"
        className={
          compact
            ? "quote-share__trigger quote-share__trigger--compact"
            : "quote-share__trigger"
        }
        onClick={handleButton}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Share this quote"
        title="Share this quote"
      >
        <span aria-hidden="true">↗</span>
        {!compact && <span className="quote-share__trigger-label"> Share</span>}
      </button>
      {open && (
        <div className="quote-share__menu" role="menu">
          <div className="quote-share__head">Share this quote</div>
          {SHARE_TARGETS.map((t) => (
            <a
              key={t.key}
              role="menuitem"
              className="quote-share__item"
              href={t.href(absoluteUrl, shareText)}
              target={t.newTab ? "_blank" : undefined}
              rel={t.newTab ? "noopener noreferrer" : undefined}
              onClick={() => setOpen(false)}
            >
              <span className="quote-share__icon" aria-hidden="true">{t.icon}</span>
              <span>{t.label}</span>
            </a>
          ))}
          <button
            type="button"
            role="menuitem"
            className="quote-share__item quote-share__item--copy"
            onClick={() => copy("quote")}
          >
            <span className="quote-share__icon" aria-hidden="true">📋</span>
            <span>{copied === "quote" ? "Copied quote!" : "Copy quote + link"}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="quote-share__item quote-share__item--copy"
            onClick={() => copy("link")}
          >
            <span className="quote-share__icon" aria-hidden="true">🔗</span>
            <span>{copied === "link" ? "Copied!" : "Copy link"}</span>
          </button>
          {(videoUrl || hansardUrl) && <div className="quote-share__sep" role="separator" />}
          {videoUrl && (
            <a
              role="menuitem"
              className="quote-share__item"
              href={videoUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              title="Open the official Parliament video at this statement"
            >
              <span className="quote-share__icon" aria-hidden="true">▶</span>
              <span>Watch on Parliament's site ↗</span>
            </a>
          )}
          {hansardUrl && (
            <a
              role="menuitem"
              className="quote-share__item"
              href={hansardUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
            >
              <span className="quote-share__icon" aria-hidden="true">📜</span>
              <span>Open on Hansard ↗</span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}
