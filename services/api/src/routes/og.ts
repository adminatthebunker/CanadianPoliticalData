import type { FastifyInstance } from "fastify";
import { Resvg } from "@resvg/resvg-js";
import { query, queryOne } from "../db.js";

type TierCounts = Record<string, number>;

interface CachedImage {
  png: Buffer;
  at: number;
}

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
let cache: CachedImage | null = null;

// Speech share-card cache: keyed on `${speech_id}|${chunk_id||''}`. Cards
// don't change once a speech is ingested, but we cap entries to keep memory
// bounded under social-crawler hammer-loads.
const SPEECH_CARD_TTL_MS = 60 * 60 * 1000; // 1 hour
const SPEECH_CARD_MAX = 256;
const speechCardCache = new Map<string, CachedImage>();
function speechCardGet(key: string): Buffer | null {
  const hit = speechCardCache.get(key);
  if (!hit) return null;
  if (Date.now() - hit.at > SPEECH_CARD_TTL_MS) {
    speechCardCache.delete(key);
    return null;
  }
  return hit.png;
}
function speechCardSet(key: string, png: Buffer) {
  if (speechCardCache.size >= SPEECH_CARD_MAX) {
    const oldest = speechCardCache.keys().next().value;
    if (oldest) speechCardCache.delete(oldest);
  }
  speechCardCache.set(key, { png, at: Date.now() });
}

const ID_RE = /^[0-9a-f-]{36}$/i;

const PARTY_HEX: Record<string, string> = {
  lib: "#d71920",
  liberal: "#d71920",
  cpc: "#1a4782",
  con: "#1a4782",
  conservative: "#1a4782",
  ndp: "#f37021",
  npd: "#f37021",
  bq: "#33b2cc",
  gp: "#3d9b35",
  grn: "#3d9b35",
  green: "#3d9b35",
  ppc: "#4a3590",
};

function partyColor(party: string | null): string {
  if (!party) return "#64748b";
  return PARTY_HEX[party.toLowerCase()] ?? "#64748b";
}

async function gatherStats(): Promise<{
  pctNotCanadian: number;
  tiers: TierCounts;
  totalPoliticians: number;
  uniqueHostnames: number;
}> {
  const totalRow = (await query<{ total: number }>(
    `SELECT COUNT(*)::int AS total FROM politicians WHERE is_active=true`
  ))[0];

  const polTiers = await query<{ tier: number; n: number }>(
    `WITH uniq AS (
       SELECT DISTINCT ON (mp.hostname) mp.sovereignty_tier
       FROM map_politicians mp
       JOIN websites w ON w.id = mp.website_id
       WHERE mp.sovereignty_tier IS NOT NULL
         AND COALESCE(w.label, '') <> 'shared_official'
       ORDER BY mp.hostname, mp.scanned_at DESC
     )
     SELECT sovereignty_tier AS tier, COUNT(*)::int AS n
     FROM uniq GROUP BY sovereignty_tier ORDER BY sovereignty_tier`
  );

  const notCanadian = await query<{ pct: number }>(
    `WITH uniq AS (
       SELECT DISTINCT ON (mp.hostname) mp.sovereignty_tier
       FROM map_politicians mp
       JOIN websites w ON w.id = mp.website_id
       WHERE mp.sovereignty_tier IS NOT NULL
         AND COALESCE(w.label, '') <> 'shared_official'
       ORDER BY mp.hostname, mp.scanned_at DESC
     )
     SELECT COALESCE(
       100.0 * SUM(CASE WHEN sovereignty_tier IN (3,4,5) THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0),
       0)::float AS pct
     FROM uniq`
  );

  const tiers: TierCounts = {};
  let uniqueHostnames = 0;
  for (const r of polTiers) {
    tiers[`tier_${r.tier}`] = r.n;
    uniqueHostnames += r.n;
  }

  return {
    pctNotCanadian: Math.round((notCanadian[0]?.pct ?? 0) * 10) / 10,
    tiers,
    totalPoliticians: totalRow?.total ?? 0,
    uniqueHostnames,
  };
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function buildSvg(stats: Awaited<ReturnType<typeof gatherStats>>): string {
  const { pctNotCanadian, tiers, totalPoliticians } = stats;
  const pctDisplay = Math.round(pctNotCanadian);

  // Sovereignty tier bar chart — 5 tiers
  const tierLabels = [
    { key: "tier_1", label: "T1 Canadian", color: "#22c55e" },
    { key: "tier_2", label: "T2 Canadian-adj.", color: "#84cc16" },
    { key: "tier_3", label: "T3 Foreign", color: "#f59e0b" },
    { key: "tier_4", label: "T4 US hyperscaler", color: "#f97316" },
    { key: "tier_5", label: "T5 High-risk", color: "#e11d48" },
  ];
  const counts = tierLabels.map((t) => tiers[t.key] ?? 0);
  const maxCount = Math.max(1, ...counts);

  const chartX = 80;
  const chartY = 400;
  const chartW = 1040;
  const chartH = 110;
  const gap = 24;
  const barW = (chartW - gap * (tierLabels.length - 1)) / tierLabels.length;

  const bars = tierLabels
    .map((t, i) => {
      const c = counts[i] ?? 0;
      const h = Math.round((c / maxCount) * chartH);
      const x = chartX + i * (barW + gap);
      const y = chartY + (chartH - h);
      return `
        <rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="6" fill="${t.color}" opacity="0.9"/>
        <text x="${x + barW / 2}" y="${y - 10}" text-anchor="middle" fill="#e2e8f0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="22" font-weight="600">${c}</text>
        <text x="${x + barW / 2}" y="${chartY + chartH + 30}" text-anchor="middle" fill="#94a3b8" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="18">${escapeXml(t.label)}</text>
      `;
    })
    .join("");

  // Decorative Toronto -> Kansas City arc
  const torontoX = 820;
  const torontoY = 170;
  const kcX = 1090;
  const kcY = 260;
  const midX = (torontoX + kcX) / 2;
  const midY = Math.min(torontoY, kcY) - 50;

  const headline = `${pctDisplay}% of Canadian politicians`;
  const subHeadline = `host their websites outside Canada`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#020617"/>
      <stop offset="100%" stop-color="#0b1220"/>
    </linearGradient>
    <linearGradient id="flow" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#e11d48" stop-opacity="0.1"/>
      <stop offset="100%" stop-color="#e11d48" stop-opacity="0.8"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>

  <!-- Subtle grid -->
  <g stroke="#1e293b" stroke-width="1" opacity="0.4">
    <line x1="0" y1="100" x2="1200" y2="100"/>
    <line x1="0" y1="380" x2="1200" y2="380"/>
    <line x1="0" y1="560" x2="1200" y2="560"/>
  </g>

  <!-- Wordmark -->
  <g transform="translate(80, 70)">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="30" font-weight="700" fill="#e2e8f0">
      <tspan fill="#e11d48">🍁</tspan>
      <tspan dx="12">Canadian Political Data</tspan>
    </text>
  </g>

  <!-- Decorative Toronto -> Kansas City arc -->
  <g opacity="0.85">
    <path d="M ${torontoX} ${torontoY} Q ${midX} ${midY} ${kcX} ${kcY}"
          fill="none" stroke="url(#flow)" stroke-width="3" stroke-dasharray="4 6"/>
    <circle cx="${torontoX}" cy="${torontoY}" r="6" fill="#22c55e"/>
    <text x="${torontoX + 12}" y="${torontoY - 6}" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="16" fill="#94a3b8">Toronto</text>
    <circle cx="${kcX}" cy="${kcY}" r="6" fill="#e11d48"/>
    <text x="${kcX - 10}" y="${kcY + 26}" text-anchor="end" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="16" fill="#94a3b8">Kansas City</text>
  </g>

  <!-- Headline -->
  <g transform="translate(80, 200)">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="84" font-weight="800" fill="#e2e8f0">
      <tspan fill="#e11d48">${pctDisplay}%</tspan><tspan dx="20" fill="#e2e8f0">of Canadian</tspan>
    </text>
    <text x="0" y="84" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="56" font-weight="700" fill="#e2e8f0">politicians host websites</text>
    <text x="0" y="144" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="56" font-weight="700" fill="#94a3b8">
      <tspan>outside </tspan><tspan fill="#e11d48">Canada</tspan>.
    </text>
  </g>

  <!-- Bar chart -->
  ${bars}

  <!-- Footer -->
  <g transform="translate(80, 588)">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="20" font-weight="600" fill="#e2e8f0">canadianpoliticaldata.org</text>
    <text x="220" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="20" fill="#94a3b8">· scanned ${totalPoliticians} politicians</text>
  </g>
  <!-- suppress unused refs -->
  <!-- headline=${escapeXml(headline)} sub=${escapeXml(subHeadline)} -->
</svg>`;
}

async function renderPng(): Promise<Buffer> {
  const stats = await gatherStats();
  const svg = buildSvg(stats);
  const resvg = new Resvg(svg, {
    background: "#020617",
    fitTo: { mode: "width", value: 1200 },
    font: { loadSystemFonts: true },
  });
  return resvg.render().asPng();
}

// ── Per-speech share card ─────────────────────────────────────────
// Renders a 1200×630 OG card with the focal quote, speaker name, party
// badge, and date. Drives social-media unfurls of /speeches/:id URLs.

interface SpeechCardData {
  text: string;
  speaker: string;
  party: string | null;
  date: string | null;
  level: string;
  province: string | null;
}

async function loadSpeechCardData(
  speechId: string,
  chunkId: string | null,
): Promise<SpeechCardData | null> {
  const focal = await queryOne<{
    text: string;
    speaker_name_raw: string;
    party_at_time: string | null;
    politician_name: string | null;
    politician_party: string | null;
    spoken_at: string | null;
    level: string;
    province_territory: string | null;
  }>(
    `
    SELECT s.text, s.speaker_name_raw, s.party_at_time, s.spoken_at,
           s.level, s.province_territory,
           p.name AS politician_name, p.party AS politician_party
      FROM speeches s
      LEFT JOIN politicians p ON p.id = s.politician_id
     WHERE s.id = $1
    `,
    [speechId],
  );
  if (!focal) return null;

  let quote = focal.text;
  if (chunkId) {
    const chunk = await queryOne<{ text: string }>(
      `SELECT text FROM speech_chunks WHERE id = $1 AND speech_id = $2`,
      [chunkId, speechId],
    );
    if (chunk) quote = chunk.text;
  }

  return {
    text: quote,
    speaker: focal.politician_name ?? focal.speaker_name_raw,
    party: focal.party_at_time ?? focal.politician_party,
    date: focal.spoken_at,
    level: focal.level,
    province: focal.province_territory,
  };
}

function wrapText(text: string, maxCharsPerLine: number, maxLines: number): string[] {
  const words = text.replace(/\s+/g, " ").trim().split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if (lines.length === maxLines - 1 && (cur.length + w.length + 1) > maxCharsPerLine) break;
    if (!cur) {
      cur = w;
    } else if (cur.length + w.length + 1 <= maxCharsPerLine) {
      cur += " " + w;
    } else {
      lines.push(cur);
      cur = w;
      if (lines.length >= maxLines) break;
    }
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  if (lines.length === maxLines) {
    const last = lines[maxLines - 1];
    if (last && last.length >= maxCharsPerLine - 1) {
      lines[maxLines - 1] = last.slice(0, maxCharsPerLine - 1) + "…";
    } else if (last) {
      lines[maxLines - 1] = last + "…";
    }
  }
  return lines;
}

function formatLongDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-CA", { year: "numeric", month: "long", day: "numeric" });
}

function chamberLabel(level: string, province: string | null): string {
  if (level === "federal") return "House of Commons";
  if (level === "provincial" && province) return `${province} Legislature`;
  if (level === "provincial") return "Provincial Legislature";
  if (level === "municipal") return "Municipal Council";
  return level;
}

function buildSpeechCardSvg(data: SpeechCardData): string {
  const colour = partyColor(data.party);
  // Cap lines at 6 with a slightly tighter width so the quote always fits
  // above the speaker block. Anything longer is truncated with an ellipsis
  // (the share card is a teaser; the page itself shows the full text).
  const lines = wrapText(data.text, 52, 6);
  const speaker = escapeXml(data.speaker);
  const partyTxt = data.party ? escapeXml(data.party) : "";
  const date = escapeXml(formatLongDate(data.date));
  const venue = escapeXml(chamberLabel(data.level, data.province));

  const quoteLineY = 220;
  const lineHeight = 48;
  const quoteLines = lines
    .map(
      (l, i) =>
        `<text x="100" y="${quoteLineY + i * lineHeight}" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="34" font-weight="500" fill="#e2e8f0">${escapeXml(l)}</text>`,
    )
    .join("");

  // Speaker block sits at y = quoteLineY + (lines.length * lineHeight) + gap.
  // Computed dynamically so short quotes don't leave a gaping void and long
  // ones don't collide. Min y=520 guarantees the corner branding has room.
  const speakerY = Math.max(520, quoteLineY + lines.length * lineHeight + 30);

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#020617"/>
      <stop offset="100%" stop-color="#0b1220"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="0" y="0" width="14" height="630" fill="${colour}"/>

  <g transform="translate(100, 90)">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="22" font-weight="700" fill="#e2e8f0">
      <tspan fill="#e11d48">🍁</tspan>
      <tspan dx="10">Canadian Political Data</tspan>
    </text>
  </g>

  <g transform="translate(100, 160)">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="48" font-weight="800" fill="${colour}">"</text>
  </g>

  ${quoteLines}

  <g transform="translate(100, ${speakerY})">
    <text x="0" y="0" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="26" font-weight="700" fill="#e2e8f0">${speaker}</text>
    ${partyTxt
      ? `<rect x="${(speaker.length * 14) + 18}" y="-24" rx="6" ry="6" width="${partyTxt.length * 14 + 24}" height="30" fill="${colour}" opacity="0.92"/>
         <text x="${(speaker.length * 14) + 30}" y="-2" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="18" font-weight="700" fill="#ffffff">${partyTxt.toUpperCase()}</text>`
      : ""}
    <text x="0" y="32" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="18" fill="#94a3b8">${[venue, date].filter(Boolean).join(" · ")}</text>
  </g>

  <text x="1100" y="600" text-anchor="end" font-family="DejaVu Sans, Noto Sans, Arial, sans-serif" font-size="18" fill="#475569">canadianpoliticaldata.org</text>
</svg>`;
}

async function renderSpeechCardPng(speechId: string, chunkId: string | null): Promise<Buffer | null> {
  const data = await loadSpeechCardData(speechId, chunkId);
  if (!data) return null;
  const svg = buildSpeechCardSvg(data);
  const resvg = new Resvg(svg, {
    background: "#020617",
    fitTo: { mode: "width", value: 1200 },
    font: { loadSystemFonts: true },
  });
  return resvg.render().asPng();
}

export default async function ogRoutes(app: FastifyInstance) {
  app.get("/share", async (_req, reply) => {
    const now = Date.now();
    if (!cache || now - cache.at > CACHE_TTL_MS) {
      try {
        const png = await renderPng();
        cache = { png, at: now };
      } catch (err) {
        app.log.error({ err }, "failed to render OG image");
        if (!cache) {
          reply.code(500);
          return { error: "render_failed" };
        }
      }
    }
    reply
      .header("Content-Type", "image/png")
      .header("Cache-Control", "public, max-age=300")
      .header("Content-Length", cache!.png.length.toString());
    return reply.send(cache!.png);
  });

  app.get("/speech/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!ID_RE.test(id)) return reply.badRequest("invalid id");
    const chunkRaw = (req.query as { chunk?: string })?.chunk ?? null;
    const chunkId = chunkRaw && ID_RE.test(chunkRaw) ? chunkRaw : null;

    const cacheKey = `${id}|${chunkId ?? ""}`;
    let png = speechCardGet(cacheKey);
    if (!png) {
      try {
        const rendered = await renderSpeechCardPng(id, chunkId);
        if (!rendered) return reply.notFound();
        speechCardSet(cacheKey, rendered);
        png = rendered;
      } catch (err) {
        app.log.error({ err, id, chunkId }, "failed to render speech share card");
        reply.code(500);
        return { error: "render_failed" };
      }
    }
    reply
      .header("Content-Type", "image/png")
      .header("Cache-Control", "public, max-age=3600")
      .header("Content-Length", png.length.toString());
    return reply.send(png);
  });
}
