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
}

export function ourcommonsVideoUrl(speech: VideoEmbedSource): string | null {
  if (speech.level !== "federal") return null;
  if (speech.source_system !== "openparliament") return null;
  if (!speech.source_anchor || !/^\d+$/.test(speech.source_anchor)) return null;
  const lang = speech.language === "fr" ? "fr" : "en";
  return `https://www.ourcommons.ca/embed/${lang}/i/${speech.source_anchor}?ml=${lang}&vt=watch`;
}
