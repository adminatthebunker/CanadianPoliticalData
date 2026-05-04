// ── Procedural-noise detection ─────────────────────────────────────
// QP transcripts are punctuated by Speaker interventions, "Some hon.
// members" interjections, and chair calls to order. Hiding them lets the
// user focus on substantive Q→A pairs. Detection is intentionally
// permissive — false negatives cost nothing, false positives merely hide
// a row the user can re-enable with one click.

const PROCEDURAL_NAME_RE =
  /^(some hon\. members?|an hon\. member|the speaker|le pr[ée]sident|the chair|chairperson|the deputy speaker|hon\. members?|le greffier|the clerk)\b/i;

const PROCEDURAL_ROLE_RE =
  /^(speaker|le pr[ée]sident|chair|deputy speaker|presiding officer|clerk)\b/i;

export function isProcedural(speech: { speaker_name_raw: string; speaker_role: string | null }): boolean {
  if (PROCEDURAL_NAME_RE.test(speech.speaker_name_raw)) return true;
  if (speech.speaker_role && PROCEDURAL_ROLE_RE.test(speech.speaker_role)) return true;
  return false;
}

// ── Reading-time estimate ──────────────────────────────────────────
// 200 wpm is the conservative end of average adult reading speed for
// non-fiction prose; political transcripts read slower than novels.
export function readingTimeMinutes(wordCount: number | null | undefined): number | null {
  if (!wordCount || wordCount <= 0) return null;
  return Math.max(1, Math.round(wordCount / 200));
}
