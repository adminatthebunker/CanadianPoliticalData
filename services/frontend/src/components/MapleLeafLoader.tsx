import { useEffect, useState } from "react";

interface Props {
  label?: string;
  hint?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
  /** When true, the loader rotates a small set of Canadian puns once
   *  the load drags past the snappy-feeling threshold, and surfaces a
   *  subtle "project of bnkops.ca" attribution a bit later. Default on. */
  funny?: boolean;
}

// Kept short and lightly self-deprecating — they only appear when a
// load takes long enough that filler text is welcome rather than noisy.
// "…" is appended at render time so each entry stays naturally readable.
const PUNS: readonly string[] = [
  "Dripping the syrup",
  "Cooling the laptop",
  "Polishing the toque",
  "Asking the moose",
  "Befriending a beaver",
  "Lacing the skates",
  "Topping up the double-double",
  "Calling the loon",
] as const;

const PUN_DELAY_MS = 2500;     // wait this long before rotating in the first pun
const PUN_INTERVAL_MS = 2200;  // then swap to the next every this long
const AD_DELAY_MS = 6000;      // attribution shows after the load really drags

export function MapleLeafLoader({
  label = "Loading…",
  hint,
  size = "md",
  className,
  funny = true,
}: Props) {
  const [punIdx, setPunIdx] = useState<number | null>(null);
  const [showAd, setShowAd] = useState(false);

  useEffect(() => {
    if (!funny) return;
    // Defer everything off the initial render so a fast load (cache hit
    // or snappy server) shows the bare "Searching…" + numeric hint and
    // never reveals the silliness layer at all.
    let punTimer: number | undefined;
    const startTimer = window.setTimeout(() => {
      setPunIdx(0);
      punTimer = window.setInterval(() => {
        setPunIdx((i) => ((i ?? 0) + 1) % PUNS.length);
      }, PUN_INTERVAL_MS);
    }, PUN_DELAY_MS);
    const adTimer = window.setTimeout(() => setShowAd(true), AD_DELAY_MS);
    return () => {
      window.clearTimeout(startTimer);
      window.clearTimeout(adTimer);
      if (punTimer !== undefined) window.clearInterval(punTimer);
    };
  }, [funny]);

  const pun = punIdx !== null ? PUNS[punIdx] : null;
  // Once a pun is showing, it replaces the numeric "typically ~Xs" hint
  // — at that point the user has already seen the estimate and is ready
  // for filler that doesn't keep ticking past the predicted time.
  const finalHint = pun ? `${pun}…` : hint;

  return (
    <div
      className={`maple-loader maple-loader--${size}${className ? ` ${className}` : ""}`}
      role="status"
      aria-live="polite"
    >
      <span className="maple-loader__leaf" aria-hidden>
        🍁
      </span>
      <span className="maple-loader__label">{label}</span>
      {finalHint ? <span className="maple-loader__hint">{finalHint}</span> : null}
      {showAd && (
        <span className="maple-loader__ad">
          {"· a project of "}
          <a
            href="https://bnkops.ca"
            target="_blank"
            rel="noopener noreferrer"
          >
            bnkops.ca
          </a>
        </span>
      )}
    </div>
  );
}
