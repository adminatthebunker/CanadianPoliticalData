import { useEffect, useRef, useState } from "react";
import type { SpeechDetail } from "../hooks/useSpeech";

/**
 * Quick citation export for academic / journalistic reuse. Click →
 * popover with three formatted strings (APA, Chicago, BibTeX) + per-
 * format copy-to-clipboard. Everything is built client-side from the
 * speech's already-loaded metadata; no extra request needed.
 *
 * Why three formats: APA covers most social sciences, Chicago covers
 * legal / history, BibTeX is the LaTeX academic baseline. We pick the
 * three that span the largest share of citing audiences without
 * exploding the popover.
 */

interface Props {
  speech: SpeechDetail;
}

type Format = "apa" | "chicago" | "bibtex";

const FORMAT_LABEL: Record<Format, string> = {
  apa: "APA",
  chicago: "Chicago",
  bibtex: "BibTeX",
};

const JURISDICTION_LABEL: Record<string, string> = {
  federal: "Parliament of Canada",
  ab: "Legislative Assembly of Alberta",
  bc: "Legislative Assembly of British Columbia",
  mb: "Legislative Assembly of Manitoba",
  nb: "Legislative Assembly of New Brunswick",
  nl: "House of Assembly of Newfoundland and Labrador",
  ns: "Nova Scotia House of Assembly",
  nt: "Legislative Assembly of the Northwest Territories",
  nu: "Legislative Assembly of Nunavut",
  on: "Legislative Assembly of Ontario",
  pe: "Legislative Assembly of Prince Edward Island",
  qc: "Assemblée nationale du Québec",
  sk: "Legislative Assembly of Saskatchewan",
  yt: "Yukon Legislative Assembly",
};

function jurisdictionLabel(speech: SpeechDetail): string {
  const key = (speech.province_territory ?? speech.level ?? "federal").toLowerCase();
  return JURISDICTION_LABEL[key] ?? key;
}

function authorAPA(speech: SpeechDetail): string {
  const name = speech.politician?.name ?? speech.speaker_name_raw;
  if (!name) return "Unknown";
  // "Trudeau, J." style: last name, first-initial(s).
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;
  const last = parts[parts.length - 1];
  const initials = parts.slice(0, -1).map(p => p[0]?.toUpperCase() + ".").join(" ");
  return `${last}, ${initials}`;
}

function authorChicago(speech: SpeechDetail): string {
  // Chicago: "Last, First Middle"
  const name = speech.politician?.name ?? speech.speaker_name_raw;
  if (!name) return "Unknown";
  const parts = name.trim().split(/\s+/);
  if (parts.length < 2) return name;
  const last = parts[parts.length - 1];
  const firstMiddle = parts.slice(0, -1).join(" ");
  return `${last}, ${firstMiddle}`;
}

function bibtexKey(speech: SpeechDetail): string {
  const name = (speech.politician?.name ?? speech.speaker_name_raw ?? "speech")
    .toLowerCase()
    .replace(/[^a-z]+/g, "");
  const year = speech.spoken_at ? new Date(speech.spoken_at).getFullYear() : "nd";
  return `${name}${year}_${speech.id.slice(0, 8)}`;
}

function formatDateLong(iso: string | null): string {
  if (!iso) return "n.d.";
  try {
    return new Date(iso).toLocaleDateString("en-CA", {
      year: "numeric", month: "long", day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function formatMonthDay(iso: string | null): string {
  if (!iso) return "n.d.";
  try {
    return new Date(iso).toLocaleDateString("en-CA", {
      month: "long", day: "numeric",
    });
  } catch {
    return iso.slice(5, 10);
  }
}

function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  const mod10 = n % 10;
  if (mod10 === 1) return `${n}st`;
  if (mod10 === 2) return `${n}nd`;
  if (mod10 === 3) return `${n}rd`;
  return `${n}th`;
}

function sessionPhrase(speech: SpeechDetail): string {
  const s = speech.session;
  if (!s) return "";
  const parl = s.parliament_number;
  const sess = s.session_number;
  if (parl && sess) return `${ordinal(parl)} Parliament, ${ordinal(sess)} Session`;
  if (parl) return `${ordinal(parl)} Parliament`;
  return "";
}

function permalinkFor(speech: SpeechDetail): string {
  if (typeof window === "undefined") return `/speeches/${speech.id}`;
  return `${window.location.origin}/speeches/${speech.id}`;
}

function buildAPA(speech: SpeechDetail): string {
  // APA 7 in-text date: "Author (Year, Month Day)". The month-day is
  // intentionally without the year (year already appears once in parens).
  const author = authorAPA(speech);
  const yr = speech.spoken_at ? new Date(speech.spoken_at).getFullYear() : "n.d.";
  const monthDay = formatMonthDay(speech.spoken_at);
  const sess = sessionPhrase(speech);
  const venue = jurisdictionLabel(speech);
  const url = permalinkFor(speech);
  const sessionPart = sess ? `${venue}, ${sess}` : venue;
  return `${author} (${yr}, ${monthDay}). [Speech transcript]. ${sessionPart}. Canadian Political Data. ${url}`;
}

function buildChicago(speech: SpeechDetail): string {
  const author = authorChicago(speech);
  const dateLong = formatDateLong(speech.spoken_at);
  const sess = sessionPhrase(speech);
  const venue = jurisdictionLabel(speech);
  const url = permalinkFor(speech);
  const sessionPart = sess ? `${venue}, ${sess}` : venue;
  return `${author}. "Speech transcript." ${sessionPart}, ${dateLong}. Canadian Political Data. ${url}.`;
}

function buildBibTeX(speech: SpeechDetail): string {
  const key = bibtexKey(speech);
  const author = speech.politician?.name ?? speech.speaker_name_raw ?? "Unknown";
  const yr = speech.spoken_at ? new Date(speech.spoken_at).getFullYear() : "n.d.";
  const dateLong = formatDateLong(speech.spoken_at);
  const venue = jurisdictionLabel(speech);
  const sess = sessionPhrase(speech);
  const url = permalinkFor(speech);
  // BibTeX @misc is the safe catch-all for legislative speech; @inproceedings
  // implies conference proceedings which is wrong.
  return [
    `@misc{${key},`,
    `  author = {${author}},`,
    `  title = {Speech transcript},`,
    `  howpublished = {${venue}${sess ? `, ${sess}` : ""}},`,
    `  year = {${yr}},`,
    `  note = {${dateLong}. Canadian Political Data},`,
    `  url = {${url}}`,
    `}`,
  ].join("\n");
}

const BUILDERS: Record<Format, (s: SpeechDetail) => string> = {
  apa: buildAPA,
  chicago: buildChicago,
  bibtex: buildBibTeX,
};

export function CitationButton({ speech }: Props) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<Format | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // Click-outside + Escape close the popover. Standard popover hygiene.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function copyFormat(fmt: Format) {
    const text = BUILDERS[fmt](speech);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(fmt);
      // Reset the "Copied!" state after a beat so the next click feels live.
      setTimeout(() => {
        setCopied(prev => (prev === fmt ? null : prev));
      }, 1800);
    } catch {
      // Clipboard API can fail under non-secure contexts; fall back to
      // a selection prompt so the user can copy manually.
      window.prompt("Copy citation:", text);
    }
  }

  return (
    <div className="cite-btn">
      <button
        ref={triggerRef}
        type="button"
        className="cite-btn__trigger"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        Cite this speech
      </button>
      {open && (
        <div
          ref={popoverRef}
          className="cite-btn__popover"
          role="dialog"
          aria-label="Citation export"
        >
          {(Object.keys(BUILDERS) as Format[]).map(fmt => (
            <div key={fmt} className="cite-btn__row">
              <div className="cite-btn__row-head">
                <span className="cite-btn__row-label">{FORMAT_LABEL[fmt]}</span>
                <button
                  type="button"
                  className="cite-btn__copy"
                  onClick={() => void copyFormat(fmt)}
                >
                  {copied === fmt ? "Copied" : "Copy"}
                </button>
              </div>
              <pre className="cite-btn__row-text">{BUILDERS[fmt](speech)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
