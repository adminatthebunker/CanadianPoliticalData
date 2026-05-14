import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { z } from "zod";
import { pool, query, queryOne } from "../db.js";
import { requireAdmin, getAdminEmail } from "../middleware/user-auth.js";
import { requireCsrf } from "../lib/csrf.js";
import {
  getBalance,
  grantAdminCredit,
  grantCorrectionReward,
  listLedgerEntries,
} from "../lib/credits.js";
import { sendCorrectionApprovedEmail } from "../lib/email.js";
import { config } from "../config.js";

/**
 * Admin-panel API.
 *
 * All routes under /api/v1/admin require a signed-in user with
 * users.is_admin=true (checked by requireAdmin, which composes
 * requireUser + a per-request DB lookup). Mutating routes additionally
 * require the double-submit CSRF token via a global preHandler below.
 * Bearer-token auth was removed on 2026-04-20 — the old ADMIN_TOKEN
 * flow put the credential in localStorage, readable by any XSS on the
 * same origin.
 *
 * The command catalog the frontend uses to render forms is served
 * verbatim from /commands. To keep it in sync with the worker, the
 * canonical source is in services/scanner/src/jobs_catalog.py and this
 * endpoint mirrors it. If the catalog diverges we have a bug — the
 * plan calls out a future improvement to co-locate the catalog in one
 * place and have both runtimes read it.
 */

// Keep this catalog in lockstep with services/scanner/src/jobs_catalog.py.
// Duplication is intentional for v1 — the alternative (a live HTTP call
// to the worker) couples an admin-only feature to a container that may
// be down. Worst-case drift is "UI shows a command that's not wired" —
// the worker will refuse it with "unknown command" at run time.
const COMMAND_CATALOG = [
  // hansard
  { key: "ingest-federal-hansard", category: "hansard",
    description: "Pull federal House of Commons speeches from openparliament.ca into the `speeches` table.",
    args: [
      { name: "parliament", type: "int", required: true, help: "Parliament number (e.g. 44)." },
      { name: "session", type: "int", required: true, help: "Session within the parliament (e.g. 1)." },
      { name: "since", type: "date", required: false, help: "Only fetch debates on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch debates on/before this date." },
      { name: "limit_debates", type: "int", required: false, help: "Cap on sitting days fetched." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "ingest-ab-hansard", category: "hansard",
    description: "Pull Alberta Legislative Assembly speeches from PDF-only Hansard into the `speeches` table.",
    args: [
      { name: "legislature", type: "int", required: true, help: "AB Legislature number (e.g. 31)." },
      { name: "session", type: "int", required: true, help: "Session within the legislature (e.g. 2)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sitting PDFs fetched (newest-first)." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "enrich-ab-mlas", category: "enrichment",
    description: "Fetch /member-information?mid=NNNN per AB MLA — photo, party, constituency, cabinet/Speaker offices into politicians + politician_terms.",
    args: [
      { name: "mid", type: "string", required: false, help: "Process a single ab_assembly_mid (smoke test)." },
      { name: "limit", type: "int", required: false, help: "Cap number of MLAs processed this run." },
      { name: "delay", type: "float", required: false, help: "Seconds between page fetches (default 1.0)." },
      { name: "refresh", type: "bool", required: false, help: "Re-fetch even MLAs already enriched." },
    ],
  },
  { key: "merge-ab-presiding-stubs", category: "maintenance",
    description: "One-time reconciliation of presiding-officer-seed:AB:* stubs into their MID-keyed twins. Speeches + chunks reassign; speaker_role preserved.",
    args: [
      { name: "dry_run", type: "bool", required: false, help: "Report stub→twin pairs without modifying any rows." },
    ],
  },
  { key: "ingest-bc-hansard", category: "hansard",
    description: "Pull BC Legislative Assembly Hansard (Blues + Final HTML via LIMS HDMS) into `speeches`.",
    args: [
      { name: "parliament", type: "int", required: true, help: "BC Parliament number (e.g. 43)." },
      { name: "session", type: "int", required: true, help: "Session within the parliament (e.g. 2)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed (newest-first when capped)." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-bc-speakers", category: "hansard",
    description: "Re-resolve politician_id on BC speeches with NULL politician_id.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "resolve-bc-speakers-dated", category: "hansard",
    description: "Date-windowed BC speaker resolver. Extracts surname inline from speaker_name_raw (BC parser doesn't pre-stash surname); joins on politician_terms whose date span covers spoken_at, with cand_count=1 gate. Skips speaker_role-tagged rows. Run after pre-P35 historical-roster backfill.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "ingest-bc-former-mlas", category: "hansard",
    description: "Backfill BC pre-1992 MLA roster from Wikipedia per-parliament list articles (P29-P34, 1969-1991). Closes the pre-P35 gap left by LIMS. Inserts one politicians row per unique MLA + one politician_terms row per (politician, parliament). Idempotent.",
    args: [
      { name: "parliaments", type: "str", required: false, help: "Comma-separated parliament numbers (e.g. '29,30,31'). Default: 29-34." },
      { name: "delay", type: "float", required: false, default: 0.5, help: "Seconds between MediaWiki API calls (politeness)." },
    ],
  },
  { key: "ingest-qc-hansard", category: "hansard",
    description: "Pull Quebec Journal des débats (HTML) into `speeches`. Bilingual source, French primary.",
    args: [
      { name: "parliament", type: "int", required: true, help: "QC parliament (législature) number (e.g. 43)." },
      { name: "session", type: "int", required: true, help: "Session within the parliament (e.g. 2)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed (newest-first when capped)." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-qc-speakers", category: "hansard",
    description: "Re-resolve politician_id on QC speeches with NULL politician_id.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "resolve-qc-speakers-dated", category: "hansard",
    description: "Date-windowed QC speaker resolver. Joins NULL-politician_id speeches against politician_terms (source='assnat.qc.ca:former-mnas') whose date span covers spoken_at, with cand_count=1 gate. Run after ingest-qc-former-mnas.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "ingest-mb-hansard", category: "hansard",
    description: "Pull Manitoba Hansard (Word-exported HTML) into `speeches`. Speaker resolution via politicians.mb_assembly_slug.",
    args: [
      { name: "parliament", type: "int", required: true, help: "MB legislature number (e.g. 43)." },
      { name: "session", type: "int", required: true, help: "Session within the legislature (e.g. 3)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-mb-speakers", category: "hansard",
    description: "Re-resolve politician_id on MB Hansard speeches with NULL politician_id.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "resolve-mb-speakers-dated", category: "hansard",
    description: "Date-windowed MB speaker resolver. Uses politician_terms to disambiguate historical surnames after the former-MLAs backfill.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "resolve-on-speakers-dated", category: "hansard",
    description: "Parliament-keyed ON speaker resolver. Joins speeches.raw->'on_hansard'->>'parliament' against politician_terms source='ola.org:parliament-N' to disambiguate historical surnames after the former-MPPs backfill.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "ingest-ns-hansard", category: "hansard",
    description: "Pull Nova Scotia Hansard (HTML transcripts) into `speeches`. Speaker resolution via politicians.nslegislature_slug.",
    args: [
      { name: "parliament", type: "int", required: true, help: "NS assembly number (e.g. 65 for current)." },
      { name: "session", type: "int", required: true, help: "Session within the assembly (e.g. 1)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-ns-speakers", category: "hansard",
    description: "Re-resolve politician_id on NS Hansard speeches with NULL politician_id. Run after ingest-ns-mlas stamps new slugs.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "ingest-nl-hansard", category: "hansard",
    description: "Pull Newfoundland & Labrador Hansard (era-branching: Word-exported MsoNormal + legacy FrontPage) into `speeches`. Speaker resolution via (first_initial, surname) against date-windowed NL politician_terms.",
    args: [
      { name: "ga", type: "int", required: true, help: "NL General Assembly number (e.g. 51)." },
      { name: "session", type: "int", required: true, help: "Session within the GA (e.g. 1)." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-nl-speakers", category: "hansard",
    description: "Re-resolve politician_id on NL Hansard speeches with NULL politician_id (skips group markers + presiding-role rows).",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "ingest-nb-hansard", category: "hansard",
    description: "Pull New Brunswick Hansard (bilingual PDF) into `speeches`. English speaker lines trigger rows; French lines become body text.",
    args: [
      { name: "legislature", type: "int", required: false, help: "NB Legislature number (pair with --session)." },
      { name: "session", type: "int", required: false, help: "Session within the legislature (requires --legislature)." },
      { name: "all_sessions_in_legislature", type: "int", required: false, help: "Every session in legislature L." },
      { name: "since", type: "date", required: false, help: "Only fetch sittings on/after this date." },
      { name: "until", type: "date", required: false, help: "Only fetch sittings on/before this date." },
      { name: "limit_sittings", type: "int", required: false, help: "Cap on sittings processed (newest-first when capped)." },
      { name: "limit_speeches", type: "int", required: false, help: "Cap on TOTAL speeches ingested." },
    ],
  },
  { key: "resolve-nb-speakers", category: "hansard",
    description: "Re-resolve politician_id on NB Hansard speeches with NULL politician_id.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap speeches scanned (smoke-test aid)." },
    ],
  },
  { key: "chunk-speeches", category: "hansard",
    description: "Split speeches.text into retrievable `speech_chunks` rows (idempotent).",
    args: [{ name: "limit", type: "int", required: false, help: "Max speeches to chunk (default: all pending)." }],
  },
  { key: "embed-speech-chunks", category: "hansard",
    description: "Fill speech_chunks.embedding via TEI (Qwen3-Embedding-0.6B). ~50 c/s end-to-end.",
    args: [
      { name: "limit", type: "int", required: false, help: "Max chunks to embed this run." },
      { name: "batch_size", type: "int", required: false, default: 32, help: "Texts per TEI /embed call." },
    ],
  },
  { key: "chunk-and-embed-speeches", category: "hansard",
    description: "Chunk pending speeches then embed the resulting chunks, in one process. Atomic ordering — used by the daily 02:00 MT schedule.",
    args: [
      { name: "chunk_limit", type: "int", required: false, help: "Max speeches to chunk this run (default: all pending)." },
      { name: "embed_limit", type: "int", required: false, help: "Max chunks to embed this run (default: all pending)." },
      { name: "batch_size", type: "int", required: false, default: 32, help: "Texts per TEI /embed call." },
    ],
  },
  { key: "resolve-acting-speakers", category: "hansard",
    description: "Resolve politician_id on presiding-officer speeches (The Acting Speaker / Deputy Speaker + parenthesised MP name).",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned." },
    ],
  },
  { key: "resolve-presiding-speakers", category: "hansard",
    description: "Tie 'The Speaker' speeches to the sitting Speaker by date. Seeds politicians + politician_terms for the jurisdiction's Speaker roster, then updates NULL-politician_id rows.",
    args: [
      { name: "province", type: "enum", required: false, default: "AB", choices: ["AB", "BC", "QC", "MB", "NB", "NL", "NS", "ON", "NT", "SK"],
        help: "Jurisdiction whose Speaker roster to resolve." },
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned." },
    ],
  },
  { key: "resolve-role-only-presiding-officers", category: "hansard",
    description: "Tier-2 attribution Pass 3 — resolve role-only presiding-officer rows (e.g. 'The Deputy Speaker' with no inline name) by date-windowed lookup against ROLE_ONLY_PRESIDING_ROSTER. Covers single-person date-determined offices (Deputy Speaker, Deputy Chair of Committees) for AB / BC / MB / SK.",
    args: [
      { name: "province", type: "enum", required: false, choices: ["AB", "BC", "MB", "SK"],
        help: "2-letter code; default runs every province with a role-only roster." },
      { name: "limit", type: "int", required: false, help: "Cap candidate speeches scanned." },
    ],
  },
  { key: "relink-mb-speaker-roles", category: "hansard",
    description: "Backfill speaker_role on MB rows where the chamber parser left both speaker_role and politician_id NULL. Applies the current `_ROLE_PATTERNS` from mb_hansard_parse to each row's speaker_name_raw. Idempotent.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap candidate rows scanned." },
      { name: "dry_run", type: "bool", required: false, default: false, help: "Run SELECT + regex pass without UPDATEs." },
    ],
  },
  { key: "refresh-coverage-stats", category: "admin",
    description: "Recompute jurisdiction_sources counts and Hansard status from live data. Drives /coverage.",
    args: [],
  },
  // bills
  { key: "ingest-ns-bills", category: "bills", description: "Nova Scotia bills via Socrata.",
    args: [{ name: "limit", type: "int", required: false, help: "Max bills this run." }] },
  { key: "ingest-ns-bills-rss", category: "bills", description: "Nova Scotia current-session RSS refresh.", args: [] },
  { key: "ingest-on-bills", category: "bills", description: "Ontario P44-S1 bills via ola.org.",
    args: [
      { name: "parliament", type: "int", required: false, default: 44, help: "Parliament number." },
      { name: "session", type: "int", required: false, default: 1, help: "Session number." },
    ],
  },
  { key: "ingest-bc-bills", category: "bills", description: "BC bills via LIMS JSON.",
    args: [
      { name: "parliament", type: "int", required: false, help: "Parliament number." },
      { name: "session", type: "int", required: false, help: "Session number." },
    ],
  },
  { key: "ingest-qc-bills", category: "bills", description: "Quebec bills via donneesquebec CSV.", args: [] },
  { key: "ingest-qc-bills-rss", category: "bills", description: "Quebec current-session RSS refresh.", args: [] },
  { key: "ingest-ab-bills", category: "bills",
    description: "Alberta bills via Assembly Dashboard. Default current session; --all-sessions backfills Legislature 1+ (~137 sessions).",
    args: [
      { name: "legislature", type: "int", required: false, help: "One specific legislature (pair with --session)." },
      { name: "session", type: "int", required: false, help: "One specific session (requires --legislature)." },
      { name: "all_sessions_in_legislature", type: "int", required: false, help: "Every session within legislature L." },
      { name: "all_sessions", type: "bool", required: false, help: "Full historical backfill (Legislature 1+, ~3.5 min)." },
      { name: "delay", type: "int", required: false, default: 2, help: "Seconds between session fetches (be polite)." },
    ],
  },
  { key: "ingest-nb-bills", category: "bills",
    description: "New Brunswick bills via legnb.ca. Default current session; --all-sessions-in-legislature L backfills a whole legislature (e.g. 56 for 2006+).",
    args: [
      { name: "legislature", type: "int", required: false, help: "One specific legislature (pair with --session)." },
      { name: "session", type: "int", required: false, help: "One specific session (requires --legislature)." },
      { name: "all_sessions_in_legislature", type: "int", required: false, help: "Every session within legislature L." },
      { name: "delay", type: "int", required: false, default: 2, help: "Seconds between per-bill detail fetches." },
    ],
  },
  { key: "ingest-nl-bills", category: "bills", description: "Newfoundland & Labrador bills via assembly.nl.ca (GA index).",
    args: [
      { name: "ga", type: "int", required: false, help: "General Assembly number (pair with --session)." },
      { name: "session", type: "int", required: false, help: "Session number (requires --ga)." },
      { name: "all_sessions_in_ga", type: "int", required: false, help: "Every session in GA G." },
      { name: "all_sessions", type: "bool", required: false, help: "Every session in the index (GA 44+, ~40 sessions)." },
    ],
  },
  { key: "ingest-nt-bills", category: "bills", description: "Northwest Territories bills via ntassembly.ca (consensus gov't, no sponsors).",
    args: [
      { name: "delay", type: "int", required: false, default: 2, help: "Seconds between per-bill fetches (be polite)." },
    ],
  },
  { key: "ingest-nt-mlas", category: "hansard", description: "Stamp nt_mla_slug on existing NT politicians (current 19 from Open North) and insert ~100+ former MLAs from /members/former-members. Idempotent. Run before ingest-nt-hansard.",
    args: [
      { name: "include_former", type: "bool", required: false, default: true, help: "Walk paginated /members/former-members and insert missing MLAs." },
    ],
  },
  { key: "ingest-nt-hansard", category: "hansard", description: "Ingest NT Hansard from ntlegislativeassembly.ca. Discovery via paginated /documents-proceedings/hansard; per-sitting HTML at /hansard/hn{YYMMDD}. Speaker attribution by direct nt_mla_slug FK. Consensus government — party_at_time=NULL.",
    args: [
      { name: "limit_sittings", type: "int", required: false, help: "Cap sittings (newest-first)." },
      { name: "since", type: "str", required: false, help: "Only ingest sittings with hn_id > this (e.g. 'hn250101')." },
      { name: "url", type: "str", required: false, help: "Bypass discovery; ingest one transcript URL." },
      { name: "delay", type: "float", required: false, default: 1.0, help: "Seconds between per-sitting fetches." },
    ],
  },
  { key: "extract-nt-votes", category: "hansard", description: "Derive votes rows from already-ingested NT Hansard speeches. Detects --Carried/--Defeated Hansard convention markers; consensus-government default vote_type. Idempotent. Run after ingest-nt-hansard.",
    args: [
      { name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings (smoke-test aid)." },
    ],
  },
  { key: "extract-bc-votes", category: "hansard", description: "Derive votes from BC Hansard. Detects YEAS-N/NAYS-M division blocks + inline motion outcomes.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-ab-votes", category: "hansard", description: "Derive votes from AB Hansard. Detects [Motion carried; ...] bracket annotations.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-qc-votes", category: "hansard", description: "Derive votes from QC Hansard (French). Detects Pour:N / Contre:N tallies + motion adoptée/rejetée + à l'unanimité.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-on-votes", category: "hansard", description: "Derive votes from ON Hansard. Inline motion outcomes + rare Yeas/Nays tallies.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-mb-votes", category: "hansard", description: "Derive votes from MB Hansard. Consensus-shape inline 'motion carried'.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-ns-votes", category: "hansard", description: "Derive votes from NS Hansard. Consensus-shape inline 'motion carried'.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-nl-votes", category: "hansard", description: "Derive votes from NL Hansard. Mixed consensus + occasional division.",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-nb-votes", category: "hansard", description: "Derive votes from NB Hansard (bilingual EN/FR).",
    args: [{ name: "limit_sittings", type: "int", required: false, help: "Cap to most-recent N sittings." }] },
  { key: "extract-federal-votes", category: "hansard", description: "Extract federal votes + per-MP positions from openparliament.ca structured JSON. Politician FK by openparliament_slug exact match; bill FK by bill_url. vote_type='division' with populated tallies and vote_positions. Idempotent.",
    args: [
      { name: "session", type: "str", required: false, help: "Parliament-session slug like '44-1'. Default: current." },
      { name: "limit_votes", type: "int", required: false, help: "Cap votes processed (newest-first; smoke-test aid)." },
      { name: "delay", type: "float", required: false, default: 0.5, help: "Seconds between API calls." },
    ],
  },
  { key: "ingest-federal-bill-events", category: "bills", description: "Federal bill stage events from parl.ca/LegisInfo XML. One HTTP GET per session yields ~7 milestones per bill (1st/2nd/3rd reading × House+Senate + royal assent). FK via bills.raw->>'legisinfo_id'. Idempotent. Run after ingest-federal-bills.",
    args: [
      { name: "parliament", type: "int", required: false, help: "Parliament number (default: current)." },
      { name: "session", type: "int", required: false, help: "Session number (default: current)." },
      { name: "all_sessions", type: "bool", required: false, help: "Walk every federal session in legislative_sessions." },
    ],
  },
  { key: "fetch-qc-bill-introduced-dates", category: "bills", description: "Fetch QC bill detail pages and extract introduction-sitting dates from the <h3>Introduction</h3> block. Inserts bill_events first_reading rows, then rolls up onto bills.introduced_date. Sibling of fetch-qc-bill-sponsors. Idempotent.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap bills scanned (default: every undated bill)." },
      { name: "delay", type: "float", required: false, default: 1.5, help: "Seconds between HTTP requests." },
    ],
  },
  { key: "relink-bill-introduced-dates", category: "bills", description: "Pure-SQL backfill of bills.introduced_date from bill_events first_reading rows. Cross-jurisdictional, idempotent. Closes denormalisation gaps where events exist but the column is null.",
    args: [
      { name: "levels", type: "str", required: false, help: "Comma-separated levels (e.g. 'provincial,federal'). Default: all." },
      { name: "provinces", type: "str", required: false, help: "Comma-separated province codes (e.g. 'MB,NS'). Default: all." },
    ],
  },
  { key: "ingest-nu-bills", category: "bills", description: "Nunavut bills via assembly.nu.ca (consensus gov't, no sponsors; multilingual).",
    args: [
      { name: "assembly", type: "int", required: false, help: "Assembly number (default: current)." },
      { name: "session", type: "int", required: false, help: "Session number (default: current)." },
    ],
  },
  { key: "ingest-mb-bills", category: "bills",
    description: "Manitoba bills roster via web2.gov.mb.ca. Sponsors on index only; stage dates come from parse-mb-bill-events.",
    args: [
      { name: "parliament", type: "int", required: false, default: 43, help: "Legislature number (default: 43, current)." },
      { name: "session", type: "int", required: false, default: 3, help: "Session number (default: 3, current)." },
    ],
  },
  { key: "fetch-mb-billstatus-pdf", category: "bills",
    description: "Download MB billstatus.pdf into the scanner's PDF cache (once per UTC day).",
    args: [] },
  { key: "parse-mb-bill-events", category: "bills",
    description: "Parse MB billstatus.pdf → bill_events with real stage dates. Requires ingest-mb-bills first.",
    args: [
      { name: "parliament", type: "int", required: false, default: 43, help: "Legislature number (default: 43, current)." },
      { name: "session", type: "int", required: false, default: 3, help: "Session number (default: 3, current)." },
    ],
  },
  { key: "resolve-mb-bill-sponsors", category: "bills",
    description: "Link unresolved MB bill_sponsors to politicians (slug join + name-fuzz fallback).",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap on rows scanned this run (default: all unresolved)." },
    ],
  },
  // enrichment
  { key: "ingest-mps", category: "enrichment", description: "Federal MPs roster from Open North.", args: [] },
  { key: "ingest-senators", category: "enrichment", description: "Canadian Senate roster.", args: [] },
  { key: "ingest-mlas", category: "enrichment", description: "Provincial/territorial legislators via Open North.", args: [] },
  { key: "ingest-manitoba-mlas", category: "enrichment",
    description: "MB current MLA roster from Open North Represent. Closes politician_terms.ended_at + flips is_active=false for politicians dropped from the upstream roster (detect_retirements). Run weekly.",
    args: [] },
  { key: "ingest-quebec-mnas", category: "enrichment",
    description: "QC current MNA roster from Open North Represent. Closes politician_terms.ended_at + flips is_active=false for politicians dropped from the upstream roster (detect_retirements). Run weekly.",
    args: [] },
  { key: "ingest-mb-mlas", category: "enrichment",
    description: "Stamp politicians.mb_assembly_slug on existing MB rows; insert any missing MLAs. Prereq for ingest-mb-bills and ingest-mb-hansard.",
    args: [] },
  { key: "ingest-mb-former-mlas", category: "enrichment",
    description: "Backfill ~800 historical MB MLAs from mla_bio_living/deceased.html. Name-matches current MLAs before inserting; new rows keyed on lastname-firstname slugs. Prereq for pre-2023 MB Hansard backfill.",
    args: [
      { name: "living", type: "bool", required: false, default: true, help: "Include the living-MLAs bio page." },
      { name: "deceased", type: "bool", required: false, default: true, help: "Include the deceased-MLAs bio page." },
      { name: "delay", type: "float", required: false, default: 1.0, help: "Seconds between page fetches." },
    ] },
  { key: "ingest-nb-former-mlas", category: "enrichment",
    description: "Seed NB historical MLA roster (58th-60th Legislatures, 2014-2024) from a hand-curated Python literal sourced from per-Legislature Wikipedia articles. Name-matches existing current 61L MLAs before inserting; new rows keyed on a wikipedia:nb-legislature source_id. Per-Legislature term windows with mid-Leg overrides for resignations/by-elections. Prereq for Pass 4 surname resolution on pre-2024 NB Hansard.",
    args: [] },
  { key: "ingest-ns-former-mlas", category: "enrichment",
    description: "Seed NS historical MLA roster (62nd-64th General Assemblies, 2013-2024). Hand-curated Python literal sourced from per-Assembly Wikipedia articles. Name-matches existing current 65L MLAs before inserting. Per-Assembly term windows with mid-Assembly overrides. Prereq for Pass 4 surname resolution on pre-2024 NS Hansard.",
    args: [] },
  { key: "ingest-nl-former-mlas", category: "enrichment",
    description: "Seed NL historical MHA roster (50th General Assembly, 2021-2025). Hand-curated Python literal sourced from Wikipedia. Name-matches existing current 51L MHAs before inserting. Prereq for Pass 4 initial-prefix-style surname resolution on NL Hansard 2022-2025.",
    args: [] },
  { key: "ingest-on-former-mpps", category: "enrichment",
    description: "Backfill historical ON MPPs from ola.org/en/members/parliament-{N} (N=1..44, 1867-present). Fetches per-member JSON for stable field_member_id; name-matches existing ON rows so Open North current-roster entries get stamped rather than duplicated. Prereq for pre-current-Parliament ON Hansard backfill.",
    args: [
      { name: "from_parliament", type: "int", required: false, default: 1, help: "Earliest parliament to enumerate (default: 1 = 1867)." },
      { name: "until_parliament", type: "int", required: false, default: 44, help: "Latest parliament to enumerate (default: 44 = current)." },
      { name: "delay", type: "float", required: false, default: 1.0, help: "Seconds between page fetches (be polite to ola.org)." },
    ] },
  { key: "ingest-qc-former-mnas", category: "enrichment",
    description: "Backfill historical QC MNAs from assnat.qc.ca/fr/membres/notices/index*.html (16 alphabet-letter pages, ~2,500 MNAs since 1764). Per-MNA bio page is parsed via prose-regex for first/last career years; one wide-span politician_terms row inserted per MNA (source='assnat.qc.ca:former-mnas'). Prereq for resolve-qc-speakers-dated.",
    args: [
      { name: "delay", type: "float", required: false, default: 1.5, help: "Seconds between page fetches (be polite to assnat.qc.ca)." },
      { name: "limit", type: "int", required: false, help: "Cap MNAs processed this run (smoke-test aid)." },
    ] },
  { key: "enrich-bc-member-parliaments", category: "enrichment",
    description: "Stamp politician_terms for every BC (member, parliament) edge from LIMS GraphQL allMemberParliaments (~750 edges, single query). One term per edge with source='lims.leg.bc.ca:parliament-N'. Prereq: scripts/bc-enrich-historical-mlas.py for the 376-MLA historical roster.",
    args: [] },
  { key: "ingest-ns-mlas", category: "enrichment",
    description: "Stamp politicians.nslegislature_slug on seated NS MLAs by harvesting anchor slugs from current-session Hansard. Prereq for ingest-ns-hansard.",
    args: [
      { name: "parliament", type: "int", required: false, default: 65, help: "Assembly to harvest slugs from (default 65)." },
      { name: "session", type: "int", required: false, default: 1, help: "Session within the assembly (default 1)." },
      { name: "sample_sittings", type: "int", required: false, default: 5, help: "Newest sittings to scan." },
    ],
  },
  { key: "ingest-councils", category: "enrichment", description: "Municipal councillors via Open North.", args: [] },
  { key: "ingest-legislatures", category: "enrichment", description: "Full provincial/territorial legislature ingest.", args: [] },
  { key: "harvest-personal-socials", category: "enrichment", description: "Scrape personal sites for social handles.",
    args: [{ name: "limit", type: "int", required: false, help: "Max politicians this run." }] },
  // socials audit + tiered backfill
  { key: "audit-socials", category: "enrichment",
    description: "Snapshot social-media coverage; refresh v_socials_missing view.",
    args: [{ name: "no_csv", type: "bool", required: false, help: "Skip CSV export; print tables only." }] },
  { key: "enrich-socials-all", category: "enrichment",
    description: "Tier-1: wikidata + openparliament + masto-host enrichment. Zero LLM cost.", args: [] },
  { key: "probe-missing-socials", category: "enrichment",
    description: "Tier-2: pattern-probe candidate URLs for missing socials. Zero LLM cost.",
    args: [
      { name: "platform", type: "str", required: false, default: "bluesky",
        help: "bluesky | twitter | facebook | instagram | youtube | threads" },
      { name: "limit", type: "int", required: false, default: 500, help: "Max missing rows to probe this run." },
      { name: "dry_run", type: "bool", required: false, help: "Print would-be inserts without writing." },
    ] },
  { key: "agent-missing-socials", category: "enrichment",
    description: "Tier-3: Sonnet agent + web_search fills residual missing handles. Requires ANTHROPIC_API_KEY.",
    args: [
      { name: "platform", type: "str", required: false, help: "Focus one platform (omit for all-missing)." },
      { name: "batch_size", type: "int", required: false, default: 10, help: "Politicians per agent call (max 25)." },
      { name: "max_batches", type: "int", required: false, default: 20, help: "Hard cap on agent calls per run." },
      { name: "model", type: "str", required: false, help: "Override the default Claude model." },
      { name: "dry_run", type: "bool", required: false, help: "Print candidate hits without inserting." },
    ] },
  { key: "agent-missing-websites", category: "enrichment",
    description: "Tier-3: Sonnet agent + web_search finds politician personal/party websites. Search cap = 3 per politician. Requires ANTHROPIC_API_KEY.",
    args: [
      { name: "batch_size", type: "int", required: false, default: 10, help: "Politicians per agent call (max 25)." },
      { name: "max_batches", type: "int", required: false, default: 20, help: "Hard cap on agent calls per run." },
      { name: "model", type: "str", required: false, help: "Override the default Claude model." },
      { name: "dry_run", type: "bool", required: false, help: "Print candidate hits without inserting." },
    ] },
  { key: "verify-socials", category: "enrichment",
    description: "Liveness check on politician_socials URLs. Writes social_dead change rows on live→dead flips.",
    args: [
      { name: "limit", type: "int", required: false, default: 500, help: "Max rows to verify per run." },
      { name: "stale_hours", type: "int", required: false, default: 168, help: "Re-verify if older than N hours." },
    ] },
  // maintenance
  { key: "refresh-views", category: "maintenance", description: "Refresh map materialized views.", args: [] },
  { key: "seed-orgs", category: "maintenance", description: "Re-apply referendum/advocacy orgs seed.", args: [] },
  { key: "backfill-terms", category: "maintenance",
    description: "One-time: open an initial politician_terms row for every active politician without an existing open term. Prereq for party-at-time queries.",
    args: [] },
  { key: "backfill-politician-photos", category: "maintenance",
    description: "Mirror upstream politician portraits to the local /assets volume; re-fetch stale rows (>30 days) on each run. Idempotent.",
    args: [
      { name: "limit", type: "int", required: false, help: "Cap politicians processed this run." },
      { name: "stale_days", type: "int", required: false, default: 30, help: "Re-fetch if last fetch is older than N days." },
      { name: "politician_id", type: "str", required: false, help: "Process a single politician by UUID." },
      { name: "concurrency", type: "int", required: false, default: 4, help: "Parallel fetches. Per-host spacing still applies." },
    ],
  },
  { key: "gc-usage-metrics", category: "maintenance",
    description: "Drop old rows from private.gpu_samples / tei_samples (90d) and search_request_log (30d). Drives the admin /usage page retention.",
    args: [] },
  { key: "scan", category: "maintenance", description: "Infrastructure scan across tracked websites.",
    args: [
      { name: "limit", type: "int", required: false, help: "Max sites this run." },
      { name: "stale_hours", type: "int", required: false, default: 6, help: "Re-scan if older than N hours." },
    ],
  },
  { key: "dispatch-scrapes", category: "maintenance",
    description: "One tick of the scrape dispatcher: find due saved-search subscriptions and enqueue scrape_jobs + holds.",
    args: [] },
  { key: "run-scrape-jobs", category: "maintenance",
    description: "Drain up to N queued scrape_jobs (Apify or free APIs); commit or release credit holds.",
    args: [
      { name: "limit", type: "int", required: false, default: 5, help: "Max queued jobs to drain in this run." },
    ],
  },
  { key: "poll-scrape-costs", category: "maintenance",
    description: "Re-fetch Apify usageTotalUsd for succeeded scrape_jobs whose billing settled after the sync run returned.",
    args: [] },
  { key: "scrape-politician", category: "enrichment",
    description: "Enqueue + run one scrape job against a single politician (admin / operator one-shot).",
    args: [
      { name: "politician_id", type: "string", required: true, help: "UUID of public.politicians.id." },
      { name: "platform", type: "enum", required: true,
        choices: ["twitter", "bluesky", "instagram", "mastodon"] },
      { name: "user_id", type: "string", required: true, help: "UUID of private.users.id to bill (admin: pass admin user)." },
      { name: "kind", type: "enum", required: false, default: "monitoring",
        choices: ["monitoring", "preflight", "archive"],
        help: "preflight = profile probe; archive = deep history." },
      { name: "post_hint", type: "int", required: false, help: "Lifetime post-count hint for archive pricing." },
    ],
  },
];

const COMMAND_KEYS = new Set(COMMAND_CATALOG.map(c => c.key));

// ── Zod schemas ────────────────────────────────────────────────────

const jobsListQuery = z.object({
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]).optional(),
  schedule_id: z.string().uuid().optional(),
  limit: z.coerce.number().int().min(1).max(500).default(100),
});

const jobCreateBody = z.object({
  command: z.string(),
  args: z.record(z.string(), z.any()).default({}),
  priority: z.coerce.number().int().min(0).max(100).default(10),
});

const scheduleCreateBody = z.object({
  name: z.string().min(1).max(200),
  command: z.string(),
  args: z.record(z.string(), z.any()).default({}),
  cron: z.string().regex(
    /^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$/,
    "cron must be a 5-field expression (m h dom mon dow)"
  ),
  enabled: z.boolean().optional().default(true),
});

const schedulePatchBody = z.object({
  name: z.string().min(1).max(200).optional(),
  args: z.record(z.string(), z.any()).optional(),
  cron: z.string().regex(/^\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$/).optional(),
  enabled: z.boolean().optional(),
});

// ── Routes ─────────────────────────────────────────────────────────

export default async function adminRoutes(app: FastifyInstance) {
  // Gate every route on "signed-in user with is_admin=true".
  app.addHook("preHandler", requireAdmin);
  // Mutating routes additionally require CSRF. Hook order matters —
  // this runs after requireAdmin, so a non-admin caller gets 403
  // (wrong role) rather than 403 (missing CSRF), which is the more
  // useful error. GET/HEAD are safe methods per RFC 9110 §9.2.1;
  // OPTIONS is handled by @fastify/cors before we see it.
  app.addHook("preHandler", async (req: FastifyRequest, reply: FastifyReply) => {
    const m = req.method.toUpperCase();
    if (m === "GET" || m === "HEAD" || m === "OPTIONS") return;
    return requireCsrf(req, reply);
  });

  app.get("/commands", async () => ({ commands: COMMAND_CATALOG }));

  // ── Jobs ───────────────────────────────────────────────────────
  app.get("/jobs", async (req, reply) => {
    const q = jobsListQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const { status, schedule_id, limit } = q.data;

    const params: (string | number | boolean | null | string[])[] = [];
    const where: string[] = [];
    if (status) { params.push(status); where.push(`status = $${params.length}`); }
    if (schedule_id) { params.push(schedule_id); where.push(`schedule_id = $${params.length}`); }
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";
    params.push(limit);
    const rows = await query(
      `SELECT id, command, args, status, priority, schedule_id, requested_by,
              queued_at, started_at, finished_at, exit_code,
              -- size-cap the tails at list time to keep payloads small
              LEFT(COALESCE(stdout_tail,''), 500) AS stdout_snippet,
              LEFT(COALESCE(stderr_tail,''), 500) AS stderr_snippet,
              error
         FROM scanner_jobs
         ${whereSql}
         ORDER BY queued_at DESC
         LIMIT $${params.length}`,
      params as any,
    );
    return { jobs: rows };
  });

  app.post("/jobs", async (req, reply) => {
    const parsed = jobCreateBody.safeParse(req.body);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { command, args, priority } = parsed.data;
    if (!COMMAND_KEYS.has(command)) {
      return reply.badRequest(`unknown command: ${command}`);
    }
    const actor = getAdminEmail(req) ?? "admin";
    const row = await queryOne<{ id: string }>(
      `INSERT INTO scanner_jobs (command, args, status, priority, requested_by)
       VALUES ($1, $2::jsonb, 'queued', $3, $4)
       RETURNING id`,
      [command, JSON.stringify(args), priority, actor] as any,
    );
    return reply.code(201).send({ id: row?.id });
  });

  app.get("/jobs/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `SELECT id, command, args, status, priority, schedule_id, requested_by,
              queued_at, started_at, finished_at, exit_code,
              stdout_tail, stderr_tail, error
         FROM scanner_jobs WHERE id = $1`,
      [id] as any,
    );
    if (!row) return reply.notFound();
    return row;
  });

  app.post("/jobs/:id/cancel", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `UPDATE scanner_jobs
          SET status = 'cancelled', finished_at = now()
        WHERE id = $1 AND status = 'queued'
        RETURNING id, status`,
      [id] as any,
    );
    if (!row) {
      return reply.code(409).send({ error: "job not queued (already running or terminal)" });
    }
    return row;
  });

  // ── Schedules ───────────────────────────────────────────────────
  app.get("/schedules", async () => {
    const rows = await query(
      `SELECT id, name, command, args, cron, enabled,
              last_enqueued_at, next_run_at,
              created_by, created_at, updated_at
         FROM scanner_schedules
         ORDER BY name`
    );
    return { schedules: rows };
  });

  app.post("/schedules", async (req, reply) => {
    const parsed = scheduleCreateBody.safeParse(req.body);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { name, command, args, cron, enabled } = parsed.data;
    if (!COMMAND_KEYS.has(command)) {
      return reply.badRequest(`unknown command: ${command}`);
    }
    const actor = getAdminEmail(req) ?? "admin";
    const row = await queryOne<{ id: string }>(
      `INSERT INTO scanner_schedules (name, command, args, cron, enabled, created_by)
       VALUES ($1, $2, $3::jsonb, $4, $5, $6)
       RETURNING id`,
      [name, command, JSON.stringify(args), cron.trim(), enabled, actor] as any,
    );
    return reply.code(201).send({ id: row?.id });
  });

  app.patch("/schedules/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const parsed = schedulePatchBody.safeParse(req.body);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const fields: string[] = [];
    const params: (string | number | boolean | null | string[])[] = [];
    const body = parsed.data;
    if (body.name !== undefined) { params.push(body.name); fields.push(`name = $${params.length}`); }
    if (body.args !== undefined) { params.push(JSON.stringify(body.args)); fields.push(`args = $${params.length}::jsonb`); }
    if (body.cron !== undefined) {
      params.push(body.cron.trim());
      fields.push(`cron = $${params.length}`);
      // Force next_run_at recompute on the worker's next poll by clearing it.
      fields.push(`next_run_at = NULL`);
    }
    if (body.enabled !== undefined) { params.push(body.enabled); fields.push(`enabled = $${params.length}`); }
    if (!fields.length) return reply.badRequest("no fields to update");
    params.push(id);
    const row = await queryOne(
      `UPDATE scanner_schedules SET ${fields.join(", ")} WHERE id = $${params.length}
       RETURNING id, name, command, args, cron, enabled, next_run_at`,
      params as any,
    );
    if (!row) return reply.notFound();
    return row;
  });

  app.delete("/schedules/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const res = await query(
      `DELETE FROM scanner_schedules WHERE id = $1 RETURNING id`,
      [id] as any,
    );
    if (!res.length) return reply.notFound();
    return reply.code(204).send();
  });

  // ── Dashboard stats ─────────────────────────────────────────────
  app.get("/stats", async () => {
    // Single trip for low-latency dashboard load.
    const [
      speeches, chunks, jobs, jurisdictions, recentFailures,
    ] = await Promise.all([
      queryOne<{ total: number }>(`SELECT COUNT(*)::int AS total FROM speeches`),
      queryOne<{ total: number; embedded: number; pending: number }>(
        `SELECT COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE embedding IS NOT NULL)::int AS embedded,
                COUNT(*) FILTER (WHERE embedding IS NULL)::int     AS pending
           FROM speech_chunks`
      ),
      queryOne<{ queued: number; running: number; succeeded_24h: number; failed_24h: number }>(
        `SELECT
            COUNT(*) FILTER (WHERE status = 'queued')::int   AS queued,
            COUNT(*) FILTER (WHERE status = 'running')::int  AS running,
            COUNT(*) FILTER (WHERE status = 'succeeded' AND finished_at > now() - interval '24 hours')::int AS succeeded_24h,
            COUNT(*) FILTER (WHERE status = 'failed' AND finished_at > now() - interval '24 hours')::int    AS failed_24h
           FROM scanner_jobs`
      ),
      queryOne<{ live: number; total: number }>(
        `SELECT COUNT(*) FILTER (WHERE bills_status = 'live')::int AS live,
                COUNT(*)::int AS total
           FROM jurisdiction_sources`
      ),
      query(
        `SELECT id, command, finished_at, error
           FROM scanner_jobs
          WHERE status = 'failed' AND finished_at > now() - interval '24 hours'
          ORDER BY finished_at DESC LIMIT 5`
      ),
    ]);
    return {
      speeches: speeches?.total ?? 0,
      chunks: {
        total: chunks?.total ?? 0,
        embedded: chunks?.embedded ?? 0,
        pending: chunks?.pending ?? 0,
      },
      jobs: {
        queued: jobs?.queued ?? 0,
        running: jobs?.running ?? 0,
        succeeded_24h: jobs?.succeeded_24h ?? 0,
        failed_24h: jobs?.failed_24h ?? 0,
      },
      jurisdictions: {
        live: jurisdictions?.live ?? 0,
        total: jurisdictions?.total ?? 0,
      },
      recent_failures: recentFailures,
    };
  });

  // ── Operator observability: GPU + TEI + search-traffic dashboard ─
  // Backed by the gpu-sampler container (NVML + TEI /metrics scrape
  // every 30s) and the inline search-route telemetry hook. All three
  // tables live in the `private` schema; never in the public dump.
  // Frontend at /admin/usage polls /snapshot every 5s for live cards
  // + the most recent N samples for sparklines.
  app.get("/usage/snapshot", async () => {
    const [gpu, tei, searchCounts] = await Promise.all([
      queryOne<{
        sampled_at: string; mem_used_mb: number; mem_total_mb: number;
        util_gpu_pct: number; util_mem_pct: number;
        temperature_c: number | null; power_w: number | null;
      }>(
        `SELECT sampled_at, mem_used_mb, mem_total_mb, util_gpu_pct,
                util_mem_pct, temperature_c, power_w
           FROM private.gpu_samples
           ORDER BY sampled_at DESC LIMIT 1`
      ),
      queryOne<{
        sampled_at: string; queue_size: number | null;
        request_count_total: string | null;
        request_failure_total: string | null;
        request_duration_p50_ms: string | null;
        request_duration_p95_ms: string | null;
        request_duration_p99_ms: string | null;
        batch_next_size_avg: string | null;
      }>(
        `SELECT sampled_at, queue_size, request_count_total, request_failure_total,
                request_duration_p50_ms, request_duration_p95_ms,
                request_duration_p99_ms, batch_next_size_avg
           FROM private.tei_samples
           ORDER BY sampled_at DESC LIMIT 1`
      ),
      queryOne<{
        searches_5m: number; searches_60m: number; searches_24h: number;
        p50_60m: number | null; p95_60m: number | null;
        errors_60m: number;
      }>(
        `SELECT
            COUNT(*) FILTER (WHERE created_at > now() - interval '5 minutes')::int  AS searches_5m,
            COUNT(*) FILTER (WHERE created_at > now() - interval '1 hour')::int     AS searches_60m,
            COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours')::int   AS searches_24h,
            -- Postgres percentile_cont needs sorted input; the window
            -- is small enough that the sort is in-memory cheap.
            percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms)
              FILTER (WHERE created_at > now() - interval '1 hour')                 AS p50_60m,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms)
              FILTER (WHERE created_at > now() - interval '1 hour')                 AS p95_60m,
            COUNT(*) FILTER (
              WHERE created_at > now() - interval '1 hour' AND status_code >= 500
            )::int                                                                  AS errors_60m
           FROM private.search_request_log`
      ),
    ]);
    return {
      gpu: gpu ?? null,
      tei: tei ?? null,
      search: searchCounts ?? {
        searches_5m: 0, searches_60m: 0, searches_24h: 0,
        p50_60m: null, p95_60m: null, errors_60m: 0,
      },
    };
  });

  // Time-bucketed series for sparklines. The frontend picks one metric
  // per chart and a range (60 = last hour, 1440 = last day). Bucketing
  // keeps payloads bounded — a 24h x 30s sample run is 2,880 rows raw,
  // which we floor into 1-min (60m view) or 5-min (24h view) buckets.
  const usageSeriesQuery = z.object({
    metric: z.enum([
      "vram_used_mb",
      "vram_pct",
      "gpu_util_pct",
      "tei_queue",
      "tei_p95_ms",
      "search_p95_ms",
      "search_count",
    ]),
    minutes: z.coerce.number().int().min(5).max(2880).default(60),
  });

  app.get("/usage/timeseries", async (req, reply) => {
    const parsed = usageSeriesQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { metric, minutes } = parsed.data;
    const bucketSeconds = minutes <= 120 ? 60 : 300;

    let sql: string;
    switch (metric) {
      case "vram_used_mb":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM sampled_at) / $2) * $2) AS bucket_at,
                 AVG(mem_used_mb)::numeric(10,2) AS value
            FROM private.gpu_samples
           WHERE sampled_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "vram_pct":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM sampled_at) / $2) * $2) AS bucket_at,
                 (100.0 * AVG(mem_used_mb) / NULLIF(AVG(mem_total_mb), 0))::numeric(5,2) AS value
            FROM private.gpu_samples
           WHERE sampled_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "gpu_util_pct":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM sampled_at) / $2) * $2) AS bucket_at,
                 AVG(util_gpu_pct)::numeric(5,2) AS value
            FROM private.gpu_samples
           WHERE sampled_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "tei_queue":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM sampled_at) / $2) * $2) AS bucket_at,
                 AVG(queue_size)::numeric(8,2) AS value
            FROM private.tei_samples
           WHERE sampled_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "tei_p95_ms":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM sampled_at) / $2) * $2) AS bucket_at,
                 AVG(request_duration_p95_ms)::numeric(10,2) AS value
            FROM private.tei_samples
           WHERE sampled_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "search_p95_ms":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM created_at) / $2) * $2) AS bucket_at,
                 percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms)::numeric(10,2) AS value
            FROM private.search_request_log
           WHERE created_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
      case "search_count":
        sql = `
          SELECT to_timestamp(floor(extract(epoch FROM created_at) / $2) * $2) AS bucket_at,
                 COUNT(*)::numeric AS value
            FROM private.search_request_log
           WHERE created_at > now() - ($1 || ' minutes')::interval
           GROUP BY 1 ORDER BY 1`;
        break;
    }
    const rows = await query<{ bucket_at: string; value: string }>(
      sql,
      [String(minutes), bucketSeconds],
    );
    return {
      metric,
      minutes,
      bucket_seconds: bucketSeconds,
      points: rows.map(r => ({
        t: r.bucket_at,
        v: r.value === null ? null : Number(r.value),
      })),
    };
  });

  const usageSlowQuery = z.object({
    minutes: z.coerce.number().int().min(5).max(43200).default(1440),
    limit: z.coerce.number().int().min(1).max(200).default(20),
  });

  // Top-N slowest search requests in the window. Drives the
  // "what's slow lately" drill-down on the admin /usage page.
  // No raw query text exists to display — only timing + filter shape
  // + status. That's by design (privacy) and what the operator
  // actually needs for "is this a TEI bottleneck or a SQL bottleneck?"
  app.get("/usage/slow-searches", async (req, reply) => {
    const parsed = usageSlowQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { minutes, limit } = parsed.data;
    const rows = await query<{
      created_at: string; endpoint: string;
      total_ms: number; tei_ms: number | null; sql_ms: number | null;
      result_count: number | null;
      was_anchor_query: boolean; was_authenticated: boolean;
      tier: string | null; status_code: number;
      cached_embedding: boolean; has_filters: boolean;
    }>(
      `SELECT created_at, endpoint, total_ms, tei_ms, sql_ms, result_count,
              was_anchor_query, was_authenticated, tier, status_code,
              cached_embedding, has_filters
         FROM private.search_request_log
        WHERE created_at > now() - ($1 || ' minutes')::interval
        ORDER BY total_ms DESC, created_at DESC
        LIMIT $2`,
      [String(minutes), limit],
    );
    return { rows };
  });

  // ── Socials audit + review queue ───────────────────────────────
  // The Tier-2 probe and Tier-3 agent can land rows with
  // flagged_low_confidence=true. This endpoint surfaces them for
  // human spot-checking; approve (clear flag) / reject (delete).
  app.get("/socials/coverage", async () => {
    const [total, withAny, sources, platforms] = await Promise.all([
      queryOne<{ n: number }>(
        `SELECT COUNT(*)::int AS n FROM politicians WHERE is_active = true`),
      queryOne<{ n: number }>(
        `SELECT COUNT(DISTINCT politician_id)::int AS n
           FROM politician_socials
          WHERE politician_id IN (SELECT id FROM politicians WHERE is_active = true)`),
      query<{ source: string; n: number; flagged: number }>(
        `SELECT COALESCE(source, '<null>') AS source,
                COUNT(*)::int AS n,
                COUNT(*) FILTER (WHERE flagged_low_confidence = true)::int AS flagged
           FROM politician_socials
          GROUP BY source
          ORDER BY n DESC`),
      query<{ platform: string; n: number; flagged: number }>(
        `SELECT platform,
                COUNT(*)::int AS n,
                COUNT(*) FILTER (WHERE flagged_low_confidence = true)::int AS flagged
           FROM politician_socials
          GROUP BY platform
          ORDER BY n DESC`),
    ]);
    return {
      total_active: total?.n ?? 0,
      with_any_social: withAny?.n ?? 0,
      by_source: sources,
      by_platform: platforms,
    };
  });

  const flaggedListQuery = z.object({
    platform: z.string().optional(),
    limit: z.coerce.number().int().min(1).max(500).default(50),
    offset: z.coerce.number().int().min(0).default(0),
  });

  app.get("/socials/flagged", async (req, reply) => {
    const q = flaggedListQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const { platform, limit, offset } = q.data;
    const params: (string | number | boolean | null | string[])[] = [];
    const where: string[] = ["s.flagged_low_confidence = true"];
    if (platform) { params.push(platform); where.push(`s.platform = $${params.length}`); }
    params.push(limit); const limIdx = params.length;
    params.push(offset); const offIdx = params.length;
    const rows = await query(
      `SELECT s.id, s.politician_id, s.platform, s.handle, s.url,
              s.source, s.confidence::float AS confidence,
              s.evidence_url, s.discovered_at,
              p.name AS politician_name,
              p.level, p.province_territory, p.party, p.constituency_name
         FROM politician_socials s
         JOIN politicians p ON p.id = s.politician_id
        WHERE ${where.join(" AND ")}
        ORDER BY s.confidence ASC, s.discovered_at DESC NULLS LAST
        LIMIT $${limIdx} OFFSET $${offIdx}`,
      params as any,
    );
    return { items: rows };
  });

  app.post("/socials/:id/approve", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `UPDATE politician_socials
          SET flagged_low_confidence = false,
              confidence = GREATEST(confidence, 1.0),
              updated_at = now()
        WHERE id = $1
        RETURNING id, flagged_low_confidence, confidence`,
      [id] as any,
    );
    if (!row) return reply.notFound();
    return row;
  });

  app.post("/socials/:id/reject", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `DELETE FROM politician_socials WHERE id = $1 RETURNING id`,
      [id] as any,
    );
    if (!row) return reply.notFound();
    return reply.code(204).send();
  });

  // ── Websites audit + review queue ──────────────────────────────
  // Mirrors the socials review queue. The Tier-3 Sonnet websites agent
  // (agent-missing-websites) lands rows with flagged_low_confidence=true
  // when self-reported confidence is in the 0.60–0.85 band; this surface
  // is where an operator approves (clear flag) or rejects (delete) them.
  // Politician-owned rows only — the websites table is polymorphic but
  // organisations aren't part of this review surface yet.
  app.get("/websites/coverage", async () => {
    const [total, withAny, sources, labels] = await Promise.all([
      queryOne<{ n: number }>(
        `SELECT COUNT(*)::int AS n FROM politicians WHERE is_active = true`),
      queryOne<{ n: number }>(
        `SELECT COUNT(DISTINCT owner_id)::int AS n
           FROM websites
          WHERE owner_type = 'politician'
            AND is_active = true
            AND owner_id IN (SELECT id FROM politicians WHERE is_active = true)`),
      query<{ source: string; n: number; flagged: number }>(
        `SELECT COALESCE(source, '<null>') AS source,
                COUNT(*)::int AS n,
                COUNT(*) FILTER (WHERE flagged_low_confidence = true)::int AS flagged
           FROM websites
          WHERE owner_type = 'politician'
          GROUP BY source
          ORDER BY n DESC`),
      query<{ label: string; n: number; flagged: number }>(
        `SELECT COALESCE(label, '<null>') AS label,
                COUNT(*)::int AS n,
                COUNT(*) FILTER (WHERE flagged_low_confidence = true)::int AS flagged
           FROM websites
          WHERE owner_type = 'politician'
          GROUP BY label
          ORDER BY n DESC`),
    ]);
    return {
      total_active: total?.n ?? 0,
      with_any_website: withAny?.n ?? 0,
      by_source: sources,
      by_label: labels,
    };
  });

  const websitesFlaggedListQuery = z.object({
    label: z.string().optional(),
    limit: z.coerce.number().int().min(1).max(500).default(50),
    offset: z.coerce.number().int().min(0).default(0),
  });

  app.get("/websites/flagged", async (req, reply) => {
    const q = websitesFlaggedListQuery.safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);
    const { label, limit, offset } = q.data;
    const params: (string | number | boolean | null | string[])[] = [];
    const where: string[] = [
      "w.flagged_low_confidence = true",
      "w.owner_type = 'politician'",
    ];
    if (label) { params.push(label); where.push(`w.label = $${params.length}`); }
    params.push(limit); const limIdx = params.length;
    params.push(offset); const offIdx = params.length;
    const rows = await query(
      `SELECT w.id, w.owner_id AS politician_id, w.label, w.url, w.hostname,
              w.source, w.confidence::float AS confidence,
              w.evidence_url, w.discovered_at,
              p.name AS politician_name,
              p.level, p.province_territory, p.party, p.constituency_name
         FROM websites w
         JOIN politicians p ON p.id = w.owner_id
        WHERE ${where.join(" AND ")}
        ORDER BY w.confidence ASC, w.discovered_at DESC NULLS LAST
        LIMIT $${limIdx} OFFSET $${offIdx}`,
      params as any,
    );
    return { items: rows };
  });

  app.post("/websites/:id/approve", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `UPDATE websites
          SET flagged_low_confidence = false,
              confidence = GREATEST(confidence, 1.0),
              updated_at = now()
        WHERE id = $1
        RETURNING id, flagged_low_confidence, confidence`,
      [id] as any,
    );
    if (!row) return reply.notFound();
    return row;
  });

  app.post("/websites/:id/reject", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();
    const row = await queryOne(
      `DELETE FROM websites WHERE id = $1 RETURNING id`,
      [id] as any,
    );
    if (!row) return reply.notFound();
    return reply.code(204).send();
  });

  // ── Corrections review ──────────────────────────────────────────
  // List / triage / resolve user-submitted corrections. Deep-linking
  // to the subject is the frontend's responsibility (see
  // AdminCorrections.tsx) — we just surface the foreign-key fields.

  const correctionListQuery = z.object({
    status: z.enum(["pending", "triaged", "applied", "rejected", "duplicate", "spam", "all"])
      .optional()
      .default("pending"),
    limit: z.coerce.number().int().min(1).max(200).default(50),
    offset: z.coerce.number().int().min(0).default(0),
  });

  const correctionPatchBody = z.object({
    status: z.enum(["pending", "triaged", "applied", "rejected", "duplicate", "spam"]),
    reviewer_notes: z.string().trim().max(2000).optional().nullable(),
  });

  const TERMINAL_STATUSES = new Set(["applied", "rejected", "duplicate", "spam"]);

  app.get("/corrections", async (req, reply) => {
    const parsed = correctionListQuery.safeParse(req.query);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid query" });
    }
    const { status, limit, offset } = parsed.data;
    const whereSql = status === "all" ? "" : "WHERE cs.status = $1";
    const params: unknown[] = status === "all" ? [] : [status];

    const rows = await query(
      `
      SELECT cs.id, cs.subject_type, cs.subject_id, cs.issue, cs.proposed_fix,
             cs.evidence_url, cs.status, cs.reviewer_notes, cs.reviewed_by,
             cs.submitter_name, cs.submitter_email, cs.user_id, cs.source,
             cs.received_at, cs.resolved_at,
             u.email AS user_email, u.display_name AS user_display_name,
             p.name  AS politician_name
        FROM private.correction_submissions cs
        LEFT JOIN private.users u ON u.id = cs.user_id
        LEFT JOIN public.politicians p
               ON cs.subject_type = 'politician' AND p.id = cs.subject_id
      ${whereSql}
      ORDER BY cs.received_at DESC
      LIMIT ${limit} OFFSET ${offset}
      `,
      params as any,
    );
    return { corrections: rows };
  });

  app.get("/corrections/stats", async () => {
    const rows = await query<{ status: string; n: string }>(
      `SELECT status, count(*)::text AS n
         FROM private.correction_submissions
        GROUP BY status`,
    );
    const out: Record<string, number> = {
      pending: 0, triaged: 0, applied: 0, rejected: 0, duplicate: 0, spam: 0,
    };
    for (const r of rows) out[r.status] = Number(r.n);
    return out;
  });

  app.patch("/corrections/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

    const parsed = correctionPatchBody.safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid body" });
    }
    const { status, reviewer_notes } = parsed.data;

    // Single UPDATE keeps status + notes + reviewed_by + resolved_at
    // in sync. resolved_at is set only when transitioning into a
    // terminal state, and cleared if we ever walk backwards.
    const resolvedExpr = TERMINAL_STATUSES.has(status)
      ? "now()"
      : "NULL";
    const actor = getAdminEmail(req) ?? "admin";

    // The whole status-flip + credit-grant is one transaction: if
    // the reward insert fails for any reason other than the
    // idempotency unique-violation (which the helper swallows), the
    // status change rolls back with it. That keeps "correction is
    // applied in DB" and "reward row exists in ledger" in lockstep.
    interface CorrectionRowFull {
      id: string;
      subject_type: string;
      subject_id: string | null;
      issue: string;
      proposed_fix: string | null;
      evidence_url: string | null;
      status: string;
      reviewer_notes: string | null;
      reviewed_by: string | null;
      received_at: Date;
      resolved_at: Date | null;
      user_id: string | null;
      submitter_email: string | null;
    }

    const client = await pool.connect();
    let updated: CorrectionRowFull | null = null;
    let rewardGranted = false;
    let rewardAlreadyGranted = false;
    const rewardAmount = config.corrections.rewardCredits;

    try {
      await client.query("BEGIN");

      const res = await client.query<CorrectionRowFull>(
        `
        UPDATE private.correction_submissions
           SET status         = $1,
               reviewer_notes = $2,
               reviewed_by    = $3,
               resolved_at    = ${resolvedExpr}
         WHERE id = $4
         RETURNING id, subject_type, subject_id, issue, proposed_fix,
                   evidence_url, status, reviewer_notes, reviewed_by,
                   received_at, resolved_at, user_id, submitter_email
        `,
        [status, reviewer_notes ?? null, actor, id]
      );
      updated = res.rows[0] ?? null;

      if (!updated) {
        await client.query("ROLLBACK");
        return reply.notFound();
      }

      // Grant the reward only when transitioning to applied on a
      // non-anonymous row with a positive configured reward.
      if (
        status === "applied" &&
        updated.user_id &&
        rewardAmount > 0
      ) {
        const reasonNote = `Correction accepted (${updated.subject_type})`;
        const grant = await grantCorrectionReward(
          {
            userId: updated.user_id,
            correctionId: updated.id,
            credits: rewardAmount,
            reason: reasonNote,
          },
          client
        );
        rewardGranted = grant.ledgerEntryId !== null;
        rewardAlreadyGranted = grant.alreadyGranted;
      }

      await client.query("COMMIT");
    } catch (err) {
      await client.query("ROLLBACK").catch(() => {});
      throw err;
    } finally {
      client.release();
    }

    // Fire-and-forget notification email. Only on fresh grants —
    // idempotent re-runs don't re-email. Suppressed when the user's
    // address has hard-bounced (mirrors alerts-worker discipline).
    if (rewardGranted && updated?.user_id) {
      void (async () => {
        try {
          const recipient = await queryOne<{
            email: string;
            display_name: string | null;
            email_bounced_at: Date | null;
            balance: string | null;
          }>(
            `SELECT u.email,
                    u.display_name,
                    u.email_bounced_at,
                    (SELECT COALESCE(SUM(delta), 0)::text
                       FROM private.credit_ledger
                      WHERE user_id = u.id
                        AND state IN ('committed','held')) AS balance
               FROM private.users u
              WHERE u.id = $1`,
            [updated!.user_id!]
          );
          if (!recipient) {
            req.log.warn(
              { correction_id: updated!.id },
              "[correction-reward] user row missing for notification"
            );
            return;
          }
          if (recipient.email_bounced_at) {
            req.log.warn(
              { correction_id: updated!.id, user_id: updated!.user_id },
              "[correction-reward] skipping email — address has hard-bounced"
            );
            return;
          }
          await sendCorrectionApprovedEmail(
            {
              to: recipient.email,
              displayName: recipient.display_name,
              correctionIssue: updated!.issue,
              creditsGranted: rewardAmount,
              newBalance: Number(recipient.balance ?? 0),
              accountUrl: `${config.publicSiteUrl}/account/credits`,
            },
            req.log
          );
          req.log.info(
            { correction_id: updated!.id, user_id: updated!.user_id },
            "[correction-reward] notification email dispatched"
          );
        } catch (err) {
          req.log.warn(
            { err, correction_id: updated!.id },
            "[correction-reward] email dispatch failed — credit grant unaffected"
          );
        }
      })();
    }

    // Strip user_id + submitter_email from the response — the
    // existing admin correction list has its own enriched endpoint,
    // and we don't need to start shipping PII here that wasn't
    // previously returned.
    const {
      user_id: _uid,
      submitter_email: _semail,
      ...publicFields
    } = updated;

    return reply.send({
      ...publicFields,
      credit_reward: {
        credits: rewardAmount,
        granted: rewardGranted,
        already_granted: rewardAlreadyGranted,
        eligible: status === "applied" && Boolean(updated.user_id),
      },
    });
  });

  // ── Users (for credit grants + rate-limit tier adjustments) ────
  //
  // Scoped to what the billing-rail admin UI needs: email search
  // picker, per-user detail with balance + ledger, credit grant,
  // rate-limit tier bump. Non-admin users see nothing from these —
  // requireAdmin gates the whole router.

  app.get("/users", async (req, reply) => {
    const q = z
      .object({
        q: z.string().trim().min(1).max(200).optional(),
        limit: z.coerce.number().int().min(1).max(100).default(20),
      })
      .safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);

    const params: (string | number | boolean | null | string[])[] = [];
    const conditions: string[] = [];
    if (q.data.q) {
      params.push(`%${q.data.q.toLowerCase()}%`);
      conditions.push(`email ILIKE $${params.length}`);
    }
    params.push(q.data.limit);
    const whereSql = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    const rows = await query(
      `SELECT id, email, display_name, is_admin, rate_limit_tier,
              stripe_customer_id, created_at, last_login_at
         FROM private.users
         ${whereSql}
         ORDER BY created_at DESC
         LIMIT $${params.length}`,
      params as any,
    );
    return { users: rows };
  });

  app.get("/users/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

    const user = await queryOne(
      `SELECT id, email, display_name, is_admin, rate_limit_tier,
              stripe_customer_id, created_at, last_login_at
         FROM private.users WHERE id = $1`,
      [id],
    );
    if (!user) return reply.notFound();

    const [balance, history] = await Promise.all([
      getBalance(id),
      listLedgerEntries(id, 100),
    ]);
    return { user, balance, ledger: history };
  });

  app.post("/users/:id/grant-credits", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

    const parsed = z
      .object({
        amount: z.number().int().positive().max(100_000),
        reason: z.string().trim().min(3).max(500),
      })
      .safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
    }

    const target = await queryOne<{ id: string }>(
      `SELECT id FROM private.users WHERE id = $1`,
      [id],
    );
    if (!target) return reply.notFound();

    // The acting admin's id — pulled from the request after
    // requireAdmin has validated the session. We need the id (not
    // just email) for the created_by_admin_id FK.
    const actingAdminEmail = getAdminEmail(req) ?? null;
    if (!actingAdminEmail) return reply.code(403).send({ error: "admin identity lost" });
    const actingAdmin = await queryOne<{ id: string }>(
      `SELECT id FROM private.users WHERE email = $1`,
      [actingAdminEmail],
    );
    if (!actingAdmin) return reply.code(403).send({ error: "admin row missing" });

    const ledgerId = await grantAdminCredit({
      userId: id,
      adminId: actingAdmin.id,
      credits: parsed.data.amount,
      reason: parsed.data.reason,
    });

    req.log.info(
      { target_user_id: id, admin_email: actingAdminEmail, amount: parsed.data.amount, ledger_id: ledgerId },
      "[admin] credits granted",
    );

    const balance = await getBalance(id);
    return reply.send({ ledger_entry_id: ledgerId, balance });
  });

  app.patch("/users/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

    const parsed = z
      .object({
        rate_limit_tier: z.enum(["default", "extended", "unlimited", "suspended"]),
      })
      .safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid body" });
    }

    const row = await queryOne(
      `UPDATE private.users
          SET rate_limit_tier = $1
        WHERE id = $2
        RETURNING id, email, rate_limit_tier`,
      [parsed.data.rate_limit_tier, id],
    );
    if (!row) return reply.notFound();

    req.log.info(
      { target_user_id: id, tier: parsed.data.rate_limit_tier, admin: getAdminEmail(req) },
      "[admin] rate_limit_tier updated",
    );
    return row;
  });

  // ── Rate-limit increase requests ───────────────────────────────

  app.get("/rate-limit-requests", async (req, reply) => {
    const q = z
      .object({
        status: z.enum(["pending", "approved", "denied"]).optional(),
        limit: z.coerce.number().int().min(1).max(100).default(50),
      })
      .safeParse(req.query);
    if (!q.success) return reply.badRequest(q.error.message);

    const params: (string | number | boolean | null | string[])[] = [];
    const conditions: string[] = [];
    if (q.data.status) {
      params.push(q.data.status);
      conditions.push(`r.status = $${params.length}`);
    }
    params.push(q.data.limit);
    const whereSql = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
    const rows = await query(
      `SELECT r.id, r.user_id, u.email, r.reason, r.requested_tier,
              r.status, r.admin_response, r.created_at, r.resolved_at
         FROM private.rate_limit_increase_requests r
         JOIN private.users u ON u.id = r.user_id
         ${whereSql}
         ORDER BY r.created_at DESC
         LIMIT $${params.length}`,
      params as any,
    );
    return { requests: rows };
  });

  app.patch("/rate-limit-requests/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!/^[0-9a-f-]{36}$/i.test(id)) return reply.notFound();

    const parsed = z
      .object({
        status: z.enum(["approved", "denied"]),
        admin_response: z.string().trim().min(1).max(1000),
        // When approving, the admin can also bump the user's tier in
        // the same action. Declined requests just update the request
        // row and leave the user's tier untouched.
        apply_tier: z.enum(["extended", "unlimited"]).optional(),
      })
      .safeParse(req.body);
    if (!parsed.success) {
      return reply.code(400).send({ error: "invalid body", details: parsed.error.flatten() });
    }

    const actingAdminEmail = getAdminEmail(req) ?? null;
    if (!actingAdminEmail) return reply.code(403).send({ error: "admin identity lost" });
    const actingAdmin = await queryOne<{ id: string }>(
      `SELECT id FROM private.users WHERE email = $1`,
      [actingAdminEmail],
    );
    if (!actingAdmin) return reply.code(403).send({ error: "admin row missing" });

    const requestRow = await queryOne<{ user_id: string; status: string }>(
      `SELECT user_id, status FROM private.rate_limit_increase_requests WHERE id = $1`,
      [id],
    );
    if (!requestRow) return reply.notFound();
    if (requestRow.status !== "pending") {
      return reply.code(409).send({ error: `request already ${requestRow.status}` });
    }

    const updated = await queryOne(
      `UPDATE private.rate_limit_increase_requests
          SET status         = $1,
              admin_response = $2,
              resolved_by    = $3,
              resolved_at    = now()
        WHERE id = $4
        RETURNING id, user_id, status, requested_tier, admin_response,
                  resolved_at`,
      [parsed.data.status, parsed.data.admin_response, actingAdmin.id, id],
    );

    if (parsed.data.status === "approved" && parsed.data.apply_tier) {
      await query(
        `UPDATE private.users SET rate_limit_tier = $1 WHERE id = $2`,
        [parsed.data.apply_tier, requestRow.user_id],
      );
    }

    return updated;
  });

  // ── Reports (premium, phase 1b) ────────────────────────────────
  // Operator triage surface for the /reports flow. Read-only listing
  // and detail; refund flips the hold (or grants a compensating
  // admin_credit row if the hold has already committed). Bug reports
  // queue lives here too.

  const reportsListQuery = z.object({
    status: z.enum(["queued", "running", "succeeded", "failed", "cancelled", "refunded"]).optional(),
    q: z.string().trim().optional(),
    limit: z.coerce.number().int().min(1).max(200).default(50),
  });

  app.get("/reports", async (req, reply) => {
    const parsed = reportsListQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const { status, q, limit } = parsed.data;
    const conds: string[] = [];
    const params: (string | number | boolean | null | string[])[] = [];
    if (status) {
      params.push(status);
      conds.push(`rj.status = $${params.length}`);
    }
    if (q) {
      params.push(`%${q}%`);
      conds.push(`(u.email ILIKE $${params.length} OR rj.query ILIKE $${params.length})`);
    }
    params.push(limit);
    const where = conds.length ? `WHERE ${conds.join(" AND ")}` : "";
    return await query(
      `SELECT rj.id, rj.user_id, u.email AS user_email,
              rj.politician_id, p.name AS politician_name,
              rj.query, rj.status, rj.estimated_credits, rj.chunk_count_actual,
              rj.model_used, rj.tokens_in, rj.tokens_out,
              rj.created_at, rj.finished_at, rj.error,
              rj.hold_ledger_id
         FROM private.report_jobs rj
         JOIN private.users u       ON u.id = rj.user_id
         JOIN public.politicians p ON p.id = rj.politician_id
         ${where}
        ORDER BY rj.created_at DESC
        LIMIT $${params.length}`,
      params,
    );
  });

  app.get<{ Params: { id: string } }>("/reports/:id", async (req, reply) => {
    const id = req.params.id;
    const row = await queryOne(
      `SELECT rj.*, u.email AS user_email, p.name AS politician_name
         FROM private.report_jobs rj
         JOIN private.users u       ON u.id = rj.user_id
         JOIN public.politicians p ON p.id = rj.politician_id
        WHERE rj.id = $1`,
      [id],
    );
    if (!row) return reply.notFound();
    return row;
  });

  const refundBody = z.object({
    reason: z.string().trim().min(3).max(500),
  });

  // Refund a report:
  //   - If the hold is still 'held', flip it to 'refunded' and mark the
  //     job 'refunded' (releaseHold path).
  //   - If the hold is already 'committed' (worker succeeded then user
  //     reports a problem), insert a compensating 'admin_credit' row
  //     for the same amount — never un-commit a state-flipped row.
  app.post<{ Params: { id: string }; Body: { reason: string } }>(
    "/reports/:id/refund",
    async (req, reply) => {
      const id = req.params.id;
      const parsed = refundBody.safeParse(req.body);
      if (!parsed.success) return reply.badRequest(parsed.error.message);

      const job = await queryOne<{
        id: string;
        user_id: string;
        status: string;
        estimated_credits: number;
        hold_ledger_id: string | null;
      }>(
        `SELECT id, user_id, status, estimated_credits, hold_ledger_id
           FROM private.report_jobs
          WHERE id = $1`,
        [id],
      );
      if (!job) return reply.notFound();

      const ledger = job.hold_ledger_id
        ? await queryOne<{ state: string }>(
            `SELECT state FROM private.credit_ledger WHERE id = $1`,
            [job.hold_ledger_id],
          )
        : null;

      const actingAdmin = await queryOne<{ id: string }>(
        `SELECT id FROM private.users WHERE email = $1 LIMIT 1`,
        [getAdminEmail(req)],
      );
      if (!actingAdmin) {
        return reply.code(500).send({ error: "acting admin not resolvable" });
      }

      if (ledger && ledger.state === "held") {
        // releaseHold path: flip held → refunded.
        await query(
          `UPDATE private.credit_ledger
              SET state = 'refunded',
                  reason = $2
            WHERE id = $1
              AND state = 'held'
              AND kind = 'report_hold'`,
          [job.hold_ledger_id, `admin refund: ${parsed.data.reason}`],
        );
        await query(
          `UPDATE private.report_jobs SET status = 'refunded' WHERE id = $1`,
          [id],
        );
        return { refunded: true, mode: "released_hold", credits: job.estimated_credits };
      }

      // Committed (or no hold): compensating admin_credit grant.
      await query(
        `INSERT INTO private.credit_ledger
             (user_id, delta, state, kind, reason, created_by_admin_id)
           VALUES ($1, $2, 'committed', 'admin_credit', $3, $4)`,
        [
          job.user_id,
          job.estimated_credits,
          `Compensating refund for report ${id}: ${parsed.data.reason}`,
          actingAdmin.id,
        ],
      );
      await query(
        `UPDATE private.report_jobs SET status = 'refunded' WHERE id = $1`,
        [id],
      );
      return { refunded: true, mode: "compensating_admin_credit", credits: job.estimated_credits };
    },
  );

  // ── Bug reports ────────────────────────────────────────────────
  const bugListQuery = z.object({
    status: z.enum(["open", "reviewing", "resolved", "dismissed"]).optional(),
    limit: z.coerce.number().int().min(1).max(200).default(50),
  });

  app.get("/bug-reports", async (req, reply) => {
    const parsed = bugListQuery.safeParse(req.query);
    if (!parsed.success) return reply.badRequest(parsed.error.message);
    const params: (string | number | boolean | null | string[])[] = [];
    let where = "";
    if (parsed.data.status) {
      params.push(parsed.data.status);
      where = `WHERE br.status = $${params.length}`;
    }
    params.push(parsed.data.limit);
    return await query(
      `SELECT br.id, br.report_id, br.user_id, u.email AS user_email,
              rj.politician_id, p.name AS politician_name, rj.query AS report_query,
              br.message, br.status, br.admin_notes, br.created_at, br.resolved_at
         FROM private.report_bug_reports br
         JOIN private.users u       ON u.id = br.user_id
         JOIN private.report_jobs rj ON rj.id = br.report_id
         JOIN public.politicians p ON p.id = rj.politician_id
         ${where}
        ORDER BY br.created_at DESC
        LIMIT $${params.length}`,
      params,
    );
  });

  const bugPatchBody = z.object({
    status: z.enum(["open", "reviewing", "resolved", "dismissed"]),
    admin_notes: z.string().trim().max(2000).nullable().optional(),
  });

  app.patch<{ Params: { id: string }; Body: { status: string; admin_notes?: string | null } }>(
    "/bug-reports/:id",
    async (req, reply) => {
      const id = req.params.id;
      const parsed = bugPatchBody.safeParse(req.body);
      if (!parsed.success) return reply.badRequest(parsed.error.message);
      const resolvedExpr =
        parsed.data.status === "resolved" || parsed.data.status === "dismissed"
          ? "now()"
          : "NULL";
      const updated = await queryOne(
        `UPDATE private.report_bug_reports
            SET status = $1,
                admin_notes = $2,
                resolved_at = ${resolvedExpr}
          WHERE id = $3
          RETURNING id, status, admin_notes, resolved_at`,
        [parsed.data.status, parsed.data.admin_notes ?? null, id],
      );
      if (!updated) return reply.notFound();
      return updated;
    },
  );
}
