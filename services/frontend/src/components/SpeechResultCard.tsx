import { Link, useSearchParams } from "react-router-dom";
import type { SpeechSearchItem, SpeechSearchSocial } from "../hooks/useSpeechSearch";
import { QuoteShareMenu } from "./QuoteShareMenu";
import { ourcommonsVideoUrl } from "../lib/videoEmbedUrl";
import { sanitizeHighlighted } from "../lib/textHighlight";

export { sanitizeHighlighted };

const PLATFORM_ICON: Record<string, string> = {
  twitter: "𝕏",
  x: "𝕏",
  facebook: "f",
  instagram: "◎",
  tiktok: "♪",
  youtube: "▶",
  linkedin: "in",
  threads: "@",
  bluesky: "🦋",
  mastodon: "🐘",
};

const PLATFORM_LABEL: Record<string, string> = {
  twitter: "X / Twitter",
  x: "X / Twitter",
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  linkedin: "LinkedIn",
  threads: "Threads",
  bluesky: "Bluesky",
  mastodon: "Mastodon",
};

function platformIcon(p: string): string {
  return PLATFORM_ICON[p.toLowerCase()] ?? "●";
}

function platformLabel(p: string): string {
  return PLATFORM_LABEL[p.toLowerCase()] ?? p;
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

/** English ordinal suffix: 1st, 2nd, 3rd, 4th … 11th, 12th, 13th, 21st. */
function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

function chamberLabel(level: string | null, prov: string | null): string | null {
  if (!level) return null;
  if (level === "federal") return "FED";
  if (level === "provincial" && prov) return prov.toUpperCase();
  if (level === "provincial") return "PROV";
  if (level === "municipal") return "MUNI";
  return level.toUpperCase();
}

/** Shorten parser-canonical role strings into compact UI badges. The
 *  parser writes "The Speaker", "Le Président", "Mr. Speaker", etc.
 *  Anything outside the known map renders verbatim, capped at 18 chars. */
function presidingRoleLabel(role: string | null): string | null {
  if (!role) return null;
  const trimmed = role.trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  if (lower === "the speaker" || lower === "speaker"
      || lower === "mr. speaker" || lower === "madam speaker" || lower === "madame speaker") {
    return "Speaker";
  }
  if (lower === "le président" || lower === "la présidente") return "Président";
  if (lower === "the deputy speaker" || lower === "deputy speaker") return "Deputy Speaker";
  if (lower === "chairperson" || lower === "the chair" || lower === "chair") return "Chair";
  return trimmed.length > 18 ? `${trimmed.slice(0, 17)}…` : trimmed;
}

export interface SpeechResultCardProps {
  item: SpeechSearchItem;
  /** Hide the photo + party badge when the card is rendered inside a
   *  politician's Speeches tab — the politician is already implied by
   *  the page context. */
  hideSpeaker?: boolean;
}

export function SpeechResultCard({ item, hideSpeaker = false }: SpeechResultCardProps) {
  const pol = item.politician;
  const date = formatDate(item.spoken_at);
  const chamber = chamberLabel(item.level, item.province_territory);
  const session = item.speech.session;
  const hansardUrl = item.speech.source_url
    ? item.speech.source_anchor
      ? `${item.speech.source_url}#${item.speech.source_anchor}`
      : item.speech.source_url
    : null;
  const [searchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const internalUrl =
    `/speeches/${item.speech_id}` +
    (q ? `?q=${encodeURIComponent(q)}` : "") +
    `#chunk-${item.chunk_id}`;
  const videoUrl = ourcommonsVideoUrl({
    source_system: item.speech.source_system,
    source_anchor: item.speech.source_anchor,
    level: item.level,
    language: item.language,
  });

  return (
    <article className="speech-result">
      {!hideSpeaker && (
        <div className="speech-result__speaker">
          {pol?.photo_url ? (
            <img
              src={pol.photo_url}
              alt=""
              className="speech-result__photo"
              loading="lazy"
              width={44}
              height={44}
            />
          ) : (
            <div className="speech-result__photo speech-result__photo--placeholder" aria-hidden="true">
              {(pol?.name ?? item.speech.speaker_name_raw).slice(0, 1)}
            </div>
          )}
          <div className="speech-result__speaker-meta">
            <div className="speech-result__speaker-name-row">
              {pol ? (
                <Link to={`/politicians/${pol.id}`} className="speech-result__speaker-name">
                  {pol.name ?? item.speech.speaker_name_raw}
                </Link>
              ) : (
                <span className="speech-result__speaker-name speech-result__speaker-name--unresolved">
                  {item.speech.speaker_name_raw}
                </span>
              )}
              {presidingRoleLabel(item.speech.speaker_role) && (
                <span
                  className="speech-result__role-badge"
                  title="Spoken in a presiding-officer role (chair speech, procedural)"
                >
                  {presidingRoleLabel(item.speech.speaker_role)}
                </span>
              )}
            </div>
            <span className="speech-result__speaker-sub">
              {item.party_at_time ?? pol?.party ?? "—"}
              {chamber ? <> · <span className="speech-result__chamber">{chamber}</span></> : null}
            </span>
            {pol?.socials && pol.socials.length > 0 && (
              <SocialIcons socials={pol.socials} speakerName={pol.name ?? item.speech.speaker_name_raw} />
            )}
          </div>
        </div>
      )}

      <div className="speech-result__meta">
        {date && <time dateTime={item.spoken_at ?? ""}>{date}</time>}
        {hideSpeaker && presidingRoleLabel(item.speech.speaker_role) && (
          <span
            className="speech-result__role-badge speech-result__role-badge--inline"
            title="Spoken in a presiding-officer role (chair speech, procedural)"
          >
            {presidingRoleLabel(item.speech.speaker_role)}
          </span>
        )}
        {session && (
          <span className="speech-result__session">
            {" · "}
            {ordinal(session.parliament_number)} Parl., Sess. {session.session_number}
          </span>
        )}
        <span className="speech-result__lang">{item.language.toUpperCase()}</span>
      </div>

      <p className="speech-result__snippet">
        {item.snippet_html ? (
          <span
            // safe: sanitizeHighlighted only re-admits <b> tags
            dangerouslySetInnerHTML={sanitizeHighlighted(item.snippet_html)}
          />
        ) : (
          item.text.slice(0, 280) + (item.text.length > 280 ? "…" : "")
        )}
      </p>

      <div className="speech-result__actions">
        <Link to={internalUrl} className="speech-result__action">
          View speech →
        </Link>
        <Link
          to={`/search?anchor_chunk_id=${item.chunk_id}`}
          className="speech-result__action speech-result__action--secondary"
          title="Use this chunk as your search — show speeches across the corpus closest to it semantically"
        >
          Find similar →
        </Link>
        {hansardUrl && (
          <a
            href={hansardUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="speech-result__action speech-result__action--secondary"
          >
            Hansard ↗
          </a>
        )}
        <QuoteShareMenu
          speakerName={pol?.name ?? item.speech.speaker_name_raw}
          dateIso={item.spoken_at}
          quoteText={item.text}
          internalUrl={internalUrl}
          videoUrl={videoUrl}
          hansardUrl={hansardUrl}
        />
        {item.similarity !== null && (
          <span className="speech-result__similarity" title="Cosine similarity to query">
            {(item.similarity * 100).toFixed(0)}% match
          </span>
        )}
      </div>
    </article>
  );
}

function SocialIcons({ socials, speakerName }: { socials: SpeechSearchSocial[]; speakerName: string }) {
  return (
    <span className="speech-result__socials" aria-label={`${speakerName} on social media`}>
      {socials.map((s) => (
        <a
          key={`${s.platform}:${s.url}`}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="speech-result__social"
          title={`${speakerName} on ${platformLabel(s.platform)}`}
          aria-label={`${speakerName} on ${platformLabel(s.platform)}`}
          onClick={(e) => e.stopPropagation()}
        >
          <span aria-hidden="true">{platformIcon(s.platform)}</span>
        </a>
      ))}
    </span>
  );
}

