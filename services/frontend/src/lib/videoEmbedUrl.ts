// Build a deep-link to the official ourcommons.ca video player for a federal
// Hansard speech. Pattern matches what openparliament.ca's statement-sharing.js
// constructs client-side from the HoC statement ID.
//
// Coverage today is federal-only because:
//   - all 1.08M federal speeches store the HoC statement ID in `source_anchor`,
//   - provincial legislatures each host their own video infra with no
//     universal ID-to-URL mapping.
//
// Returns null (no link rendered) when any precondition fails.

export interface VideoEmbedSource {
  source_system: string | null;
  source_anchor: string | null;
  level: string | null;
  language: string;
  source_url?: string | null;
}

export function ourcommonsVideoUrl(speech: VideoEmbedSource): string | null {
  if (speech.level !== "federal") return null;
  if (speech.source_system !== "openparliament") return null;
  if (!speech.source_anchor || !/^\d+$/.test(speech.source_anchor)) return null;
  const lang = speech.language === "fr" ? "fr" : "en";
  return `https://www.ourcommons.ca/embed/${lang}/i/${speech.source_anchor}?ml=${lang}&vt=watch`;
}

// Municipal YouTube-caption speeches (source_system '<city>-youtube-captions')
// store the timestamped video jump link directly in source_url
// ('...watch?v=<id>&t=<startSeconds>') — the speech source IS the video.
export function youtubeCaptionVideoUrl(speech: VideoEmbedSource): string | null {
  if (!speech.source_system?.endsWith("-youtube-captions")) return null;
  return speech.source_url ?? null;
}

export function speechVideoUrl(speech: VideoEmbedSource): string | null {
  return ourcommonsVideoUrl(speech) ?? youtubeCaptionVideoUrl(speech);
}

// External source link for a speech. Hansard pages take the anchor as a URL
// fragment; YouTube-caption sources already carry their position as a `t=`
// query param in source_url, where a fragment would just be noise.
export function externalSourceUrl(
  source_url: string | null,
  source_anchor: string | null,
  source_system: string | null,
): string | null {
  if (!source_url) return null;
  if (source_system?.endsWith("-youtube-captions")) return source_url;
  return source_anchor ? `${source_url}#${source_anchor}` : source_url;
}
