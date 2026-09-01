# Edmonton — Municipal Data Research

> Standalone research dossier for the City of Edmonton. Cross-cutting context lives in [`overview.md`](./overview.md). The eScribe surface description in [`calgary.md`](./calgary.md) is canonical; this file lists only Edmonton-specific findings.

**Council:** Edmonton City Council | **Website:** https://www.edmonton.ca/city_government | **Seats:** 13 (Mayor + 12 councillors, ward-based) | **Mayor:** Andrew Knack (2025–)

**Status snapshot (2026-08-14):** 🟢 **PILOT LIVE — first municipal speech corpus in the project.** Socrata meetings spine ingested (2,936 meetings, 2011-06 → present, five council terms), 654 meetings matched to YouTube stream VODs (2022+), 19 recent meetings' CC1 stenography captions parsed into ~10K `speeches.level='municipal'` rows with macro/recognition speaker attribution (all 13 sitting members FK-resolved). Modules: `services/scanner/src/legislative/edmonton_socrata.py` (spine) + `youtube_captions.py` (stages 5–7, CC-turn segmentation). Click chain: `ingest-edmonton-meetings` → `match-meetings-to-youtube` → `fetch-meeting-captions` → `resolve-meeting-caption-speakers`.

## The two-layer architecture (2026-08-14 probes)

**Layer 1 — structured spine: Socrata, difficulty 1/5.** The City Clerk publishes the entire eScribe meeting record as open datasets on `data.edmonton.ca` (no auth, SoQL, daily updates for the current term). The old "eScribe AJAX is opaque" blocker is moot — the portal IS the eScribe index.

Per council term (6 parallel tables each; current term updated daily):

| Layer | Current term (2025-29) | Notes |
|---|---|---|
| Meeting details | `ct7z-2r6h` | incl. future scheduled meetings, eScribe `uuid`, prebuilt agenda/minutes URLs |
| Agenda items | `6gb8-cs9c` | |
| Motions | `usf6-2n86` | `moved_by`/`seconded_by`, full text, tally in `result` |
| Voting record (long) | `abcm-eai5` | **one row per councillor per motion, yes/no/absent** |
| Voting record (wide) | `bjnf-zrh8` | per-councillor columns; renamed every term — use long form |
| Attendance | `pdbn-7hur` | 2021+ presence-implied; 2011-2021 tables have explicit Present/Absent per item |
| Attachments | `6yzb-v8z6` | → `filestream.ashx?DocumentId=` PDFs, no auth |

Cross-term: `7zht-i9ve` (meetings+items+motions denormalized, 2011-06 → end of 2021-25 term; **the 2025-29 term is absent despite the daily flag — union with the per-term tables**). ~373K roll-call vote rows total since 2011 across the five voting-record tables. Aux: `kyni-rzw4` Memos to Council (full text inline), `jv6d-khwd` Historical minutes 1995–2009 (`.doc` on webdocs.edmonton.ca — fetchable by exact path, root 403s), `5qee-kms7` 2011–2016 meeting videos (Google Drive MP4s, pre-YouTube), `yqff-55ja` membership history (stale at 2021), `e9qt-cc3j` current roster, `nydb-6rce` ward composition.

Gotchas: schema break at the 2021-25 term (integer `meeting_id` → `meeting_md5`/`uuid`/`num`); voter names are initial+surname (`"A. Knack"`); `meeting_type` carries `Special `/`- Non-Regular`/`- Continuation` variants needing normalization.

**Layer 2 — speech: YouTube livestream CC1 captions.** No transcript/timestamp exists anywhere in Socrata; captions are genuinely additive. Three meeting-room channels (rooms, not bodies):

- **Council Chamber** — `@councilchamber-cityofedmo9617` (~800 stream VODs, main corpus)
- **Councillors' Boardroom** — `@CouncillorsBoardroom-coejo7gs` (~118; **no caption tracks at all** — Agenda Review etc. need own-ASR via the ISI MP4s)
- **River Valley Room** — `UC6mgjEniA-4qOlCL30qGYJw` (~179)

Video titles carry the join key verbatim: `"July 7, 2026 - City Council - Public Hearing"` (tolerate abbreviated months, missing spaces, parenthesized qualifiers). Archive starts **2022**; 2024–2026 coverage is 85–93% of spine meetings.

**CC1 caption convention** (the load-bearing find; HTML-escaped as `&gt;&gt;` in the VTT):
- `>>` marks every speaker turn (~1,600/meeting).
- Steno **name macros** only for recurring speakers, mixed-case in an ALL-CAPS transcript: `>> Mayor Andrew Knack:`, `>> The Chair:`, `>> The Clerk:`.
- Everyone else gets a bare `>>` — attributable when the chair's recognition immediately precedes (`"COUNCILLOR PRINCIPE."` → `>> GOOD MORNING.`). Beware non-recognition tails: `SECONDED BY COUNCILLOR X.` / `THANK YOU, COUNCILLOR X.` reference, not recognize. Steno misspellings occur (`COUNSELLOR PARMA`) — fuzzy surname match (edit distance ≤ 2) against the 13-member roster absorbs them.
- Bonus: per-councillor vote readouts in captions (`"COUNCILLOR PRINCIPE IS YES"`) — cross-checkable against the Socrata voting record.
- **Attribution v2 (2026-08-14 evening): 37.8% of speeches / 31.2% of words FK-attributed** via three deterministic layers: (1) recognition grammar v2 — invitation clauses ("do you have questions", "has questions?", "go ahead"), queue readouts (last-named speaks first), thank-you+invitation hand-offs; (2) **block-alternation resolver** — question-period blocks (recognized member ↔ staff strict alternation between chair turns) with anchor-based parity re-sync (staff turns addressing the owner; "I'm out of time" countdown closers) that leaves glitched gaps NULL rather than guessing; (3) **minutes-derived chair resolution** — `enrich-edmonton-minutes` hydrates the server-rendered eScribe minutes, parses the roll-call conductor as chair + attendance + Administration delegation names into `meetings.raw->'minutes'`, and FKs 'The Chair' macro turns (0.8). Confidence tiers: macro 0.9 / recognition 0.7 / alternation 0.65 / fuzzy 0.6 / chair 0.8. Chunk `politician_id` denorm is re-synced by the enrich command (`sync_chunk_politician_scoped` gained a `level` param — it was provincial-hardcoded). Remaining unattributed is mostly *correctly* unattributed: staff answers, public-hearing speakers, tiny procedural turns. Every fetched track was CC1 (`caption_track='manual'` in `raw`); zero fell back to YouTube ASR.

**Video infra details:** eScribe meetings embed `/Players/ISIStandAlonePlayer.aspx?Id=<uuid>` → `https://video.isilive.ca/edmonton/<stream_name>.mp4` serves the **full unauthenticated meeting MP4** (own-ASR fallback for caption-less videos); ISI's `.vtt`/`.summary.txt` siblings 404 for Edmonton. Live captions run through EEG iCap (client `COECC`) — worth one email to city.clerk@edmonton.ca asking whether the raw caption archive is available (higher quality than YouTube's re-encode).

**eScribe detail pages are server-rendered** — `Meeting.aspx?Id=<uuid>&Agenda=PostMinutes` returns full minutes HTML (MovedBy/SecondedBy/MotionText markup) to plain curl. Only the calendar *listing* AJAX is opaque. Socrata supplies the UUIDs, so minutes narrative is a URL-hydration step, not a crawl. robots.txt disallows PetalBot only.

## Dead ends (probed 2026-08-14, don't re-probe)

- Tableau "Council Agenda and Motion Search" — viewer over `7zht-i9ve`; vizql bootstrap 410s behind AWS WAF. Unnecessary.
- `sirepub.edmonton.ca` / `meetings.edmonton.ca` — NXDOMAIN (retired; content migrated to Socrata + webdocs).
- councildataproject.org — US-only, zero Canadian instances. scrapers-ca `ca_ab_edmonton` — roster-only.
- `councilontheweb.edmonton.ca` — live HLS player only, no archive index.

## Attribution layers 3–4 — probes complete 2026-08-14 (see runbooks)

> **L3 BUILT 2026-08-14 evening** — `edmonton_panel_ocr.py`, stages `ocr-speaker-timeline` (480p download → keyframe OCR → ticking-gated interval JSON in `meetings.raw->'speaker_timeline'`) + `apply-panel-attribution` (audit-only). 15/19 pilot meetings timelined (~700 intervals); the rest hit transient YouTube 403 throttling — idempotent retry sweeps them up. **Design lesson the pilot forced: the panel names the floor OWNER, not the turn-level speaker** (the member's countdown ticks through staff answers), so the timeline feeds the block-alternation engine as an owner source (`make_panel_owner_lookup`), attribution='panel' (0.75) only for blocks confirmed by an independent in-block anchor, no trailing extrapolation. Direct interval→turn attribution is forbidden — the first cut credited delegation/staff answers to councillors. Voice auditor for deeper checks: `scripts/voice-audit/`.

- **Frame OCR (GO, built — see box above):** every stream is a Google Meet broadcast where the clerk screen-shares a speaker-management app — that panel is the identity source (100% precision on 61 detections, 2022–2026, both "layouts"). Key mechanics: current speaker = accent-blue box; the countdown timer is the state signal (frozen 05:00 = armed/queued, ticking = actually speaking); the panel flips 7–10 s *before* captions — align by sequence, never raw timestamp; the same frames render **named roll-call votes** (cross-check for the Socrata voting record). ~282 MB / 10–15 CPU-min per meeting. Full spec: `docs/runbooks/edmonton-frame-ocr-probe-2026-08-14.md`.
- **Diarization (GO as auditor / ≥8 s attributor; NOT-YET for caption-less):** ECAPA voiceprints hit 90.4% LOO at ≥3 s turns (98.3% at ≥8 s) after correcting the **~5 s CART caption lag** (measured; per-video, don't hardcode — jump links now start 5 s early because of it). Unknown-voice rejection correctly bounces staff/public (71.8%); staff voices form ~5–8 recurring clusters nameable via minutes/OCR. Its auditor role already caught and fixed a real alternation phase-inversion bug. Caption-less Boardroom + pre-2022 need segmentation + Whisper (GPU) — separate scope. Full numbers: `docs/runbooks/edmonton-diarization-poc-2026-08-14.md`.

## Acquisition layer (hardened 2026-08-15, post-retrospective)

- **Derivative media cache** (`media_cache.py`, compose bind `./media-cache`): one 480p fetch per meeting ever → persistent 16 kHz Opus audio + keyframe JPEGs + pts sidecar (~30-40 MB/meeting; ~25 GB full backfill). Panel OCR and the voice scripts consume the cache; fetch failures memoized in `meetings.raw->'fetch'` with exponential backoff (6h × attempts, hard stop at 8).
- **YouTube 403s root-caused**: GVS PO-token enforcement on `android_vr` since 2026-08-02. Fix shipped: `pot-provider` compose sidecar (bgutil 1.3.1) + plugin + `fetch_pot=always`, politeness flags on every yt-dlp call (`YTDLP_POLITE_ARGS`: sleep-requests 2, limit-rate 3M, single fragment, exponential retry-sleep). Verified: full-video download clean through the sidecar. Known wart: node 20 in the image is below yt-dlp's EJS minimum → harmless "no JS runtime" warning; add deno if formats ever go missing.
- **ISI CDN mapped, not yet consumed**: `probe-edmonton-media` records the ISI asset (url/etag/bytes) per meeting in `meetings.raw->'media'` (~73-75% coverage, 720p, unthrottled, range-seekable). Consumers stay on the YouTube cache key until the forced-alignment stage lands (ISI timeline differs ±minutes from the YouTube-based caption timestamps). `(etag, bytes)` is the media identity for the cutover.
- **City Clerk email drafted** (audio archive request + ISI courtesy note): `docs/runbooks/draft-email-edmonton-city-clerk.md` — operator to review/send.

## Remaining work

1. **Full caption backfill** (~630 matched meetings, 2022→) + daily schedules for spine/match/captions/resolve. Raise the per-channel enumeration cap (Council Chamber returned 796 at an 800 cap — check for truncation).
2. **Motions + roll-call votes ingest** (difficulty 1; needs the municipal bills/votes schema decision per [`overview.md`](./overview.md) § Schema implications).
3. Memos to Council full-text; eScribe minutes narrative hydration; 1995–2009 `.doc` minutes; 2011–2016 Drive videos + Boardroom meetings via own ASR.
4. Chair-identity resolution for `The Chair` turns (rotating; committee chair roster needed).

## Terms / Licensing

- Open Government Licence — City of Edmonton (attribution, permissive) for the Socrata data.
- YouTube-derived captions: fine for the single-user deployment; revisit standing before any re-publication. Captions ≠ certified verbatim record — footnote-required source (same class as Montréal sous-titrage).

## Status checklist

- [x] eScribe fingerprint confirmed — 2026-05-05
- [x] Socrata open-data backend confirmed — 2026-05-05
- [x] Socrata full meeting/motion/vote/attendance export mapped — 2026-08-14
- [x] YouTube channels found (3 rooms) + CC1 convention verified — 2026-08-14
- [x] Meetings spine ingested (2,936) + videos matched (654) — 2026-08-14
- [x] Caption pilot: 19 meetings, ~10K speeches, 13/13 members resolved — 2026-08-14
- [ ] Full caption backfill + daily schedules
- [ ] Motions/votes ingest (schema decision first)
- [ ] Pre-2022 speech via own ASR (Drive MP4s / ISI MP4s)
