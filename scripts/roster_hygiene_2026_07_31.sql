-- Roster hygiene batch — 2026-07-31
--
-- Fixes the stale-liveness rot documented across three memory files and
-- 15+ socials/websites agent runbooks (docs/runbooks/socials-agent-*,
-- websites-agent-*): fabricated open politician_terms recreated from
-- stale Open North rosters (batches created 2026-04-14 provincial-NL and
-- 2026-06-07 municipal), a 19th-century QC figure with an open 1860
-- term collecting a sitting MNA's speeches, and open terms on
-- politicians already marked inactive.
--
-- Policy notes:
--  * Fabricated terms (created months AFTER the person left office, from
--    a stale upstream roster) get a ZERO-LENGTH close
--    (ended_at = started_at): the row never described a real term, so
--    inventing a historical end date would be worse than recording
--    "administratively voided".
--  * The bulk sweep (section C) closes open terms of politicians already
--    is_active=false with an administrative close at now() — these are
--    NOT historical end dates; per-person history lives upstream.
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/roster_hygiene_2026_07_31.sql

begin;

-- ── A. Jean-Baptiste-Georges Proulx (d1e04c83) ──────────────────────
-- Orphan duplicate of af230712 (the real JBG Proulx, term properly
-- closed). Open 1860 term made the dated resolver treat him as sitting,
-- so 157 "Mme Proulx" speeches (2025-11 → 2026-04, hansard-qc) landed
-- on a man who died in 1884. The only sitting Proulx MNA is Caroline
-- Proulx (CAQ, Berthier, e13a0a45).

update politician_terms
   set ended_at = '1884-01-27T00:00:00Z'   -- his death; QC heritage record
 where id = '3bd1b352-f335-46c2-bdab-0f84d50e4f8b'
   and politician_id = 'd1e04c83-315c-44bf-a2ce-77a4fc39bcae'
   and ended_at is null;

update speeches
   set politician_id = 'e13a0a45-61ff-45be-945e-e815eb4ada51'  -- Caroline Proulx
 where politician_id = 'd1e04c83-315c-44bf-a2ce-77a4fc39bcae'
   and spoken_at >= '2000-01-01';           -- guard: only the modern misattributions

-- ── B. Fabricated open terms: zero-length close + is_active=false ──
-- Provincial NL (batch created 2026-04-14; both CONFIRMED lost their
-- seats in the 2025-10-14 NL election — Bennett recount denied by NL
-- Supreme Court; Howell lost by 595 votes):
--   Derek Bennett       2ae65b5d  term 79bd1a77
--   Krista Lynn Howell  e6caaedb  term 2e30325d
-- Municipal (batch created 2026-06-07; each individually confirmed
-- departed/defeated/deceased across websites-agent W27-W31 runbooks):
--   Gilbert Dumas (Laval; DECEASED 2019-08-20)         73f7a8e2  term 589fc208
--   André Fontaine (Terrebonne)                        6eddb96a  term 0c124db9
--   Aram Elagoz (Laval)                                8187db13  term 2582ce08
--   Christiane Yoakim (Laval; left politics 2021)      614f4e16  term b4dd4fb1
--   Claudio Benedetti (Brossard)                       e9782324  term 030cb4e9
--   Daniel Aucoin (Terrebonne)                         45876a8d  term db1092d8
--   Daniel Bourgeois (Moncton; lost May 2026)          9b5f7a7a  term 7f83a730
--   Daniel Hebert (Laval)                              d3bdaf04  term 67182e8f
--   David Neumann (Brantford; left after 2022)         20a2b633  term 9429e992
--   David Weiser (Québec City)                         7b583cb8  term 292feea1
--   Eric Morasse (Laval; replaced Nov 2025)            2ec792d1  term 3796a0b9
--   Fleur Paradis (Lévis; replaced by M. Sicotte)      30127abb  term 3fb5652d
--   Gilles Lehouillier (Lévis mayor; retired)          d40f361c  term 8cf1d7b9
--   Gordon Highet (Uxbridge; left after 2018-22 term)  b59f8cf2  term e6f68f39

update politician_terms
   set ended_at = started_at
 where ended_at is null
   and id in (
     '79bd1a77-4b6b-4143-836d-265f52760742',  -- Bennett
     '2e30325d-39ed-468b-b6b9-9c57422e0a6d',  -- Howell
     '589fc208-6d05-4c6e-b2d9-5aba9708973a',  -- Dumas
     '0c124db9-f2b5-4d70-9321-b4435fb7c946',
     '2582ce08-93bc-4c3e-9e41-c56924d0e1da',
     'b4dd4fb1-74d8-42af-ad7d-90e368640ea8',
     '030cb4e9-a214-49c3-856d-c60a9940650a',
     'db1092d8-ca25-4915-bb9a-f1dbc644e3c7',
     '7f83a730-460d-47ca-b8c3-b4f6fa37dddc',
     '67182e8f-2ded-4567-812b-40335155547f',
     '9429e992-316b-417d-ac04-4476b509998c',
     '292feea1-a6d3-4b4f-bb02-81a8601da099',
     '3796a0b9-e356-4fdd-839e-06cced8c30bd',
     '3fb5652d-6ac0-4c12-aebe-68fc819e9e8b',
     '8cf1d7b9-3c56-4644-bb6c-fb1a77656055',
     'e6f68f39-b691-4351-88da-45f175522700'
   );

update politicians
   set is_active = false
 where id in (
     '2ae65b5d-203c-48e9-a372-393d6c5dc996',  -- Bennett
     'e6caaedb-7e71-4643-a1d4-24e572d46283',  -- Howell
     '73f7a8e2-5683-4f8a-922e-743f032991ec',  -- Dumas
     '6eddb96a-261e-4d9c-8f0b-ec150573bb01',
     '8187db13-d8cd-464a-b88e-783636de42d7',
     '614f4e16-a397-4691-9d5c-703fe70775da',
     'e9782324-74ad-4ba9-9ddc-b28ac7783c57',
     '45876a8d-8269-4342-a848-a484e5e889db',
     '9b5f7a7a-f7b6-4082-ba47-a2616603c0f3',
     'd3bdaf04-ec35-471f-93cf-ead19f3b8965',
     '20a2b633-24dd-4757-8300-9fb4bdd48a4d',
     '7b583cb8-fa2f-4b7a-a878-b8636c5fb4c3',
     '2ec792d1-463e-48f9-bef1-e7bf320e7058',
     '30127abb-92d2-4259-bd92-8878777f2284',
     'd40f361c-71fb-4cd1-87eb-8c9eaf206470',
     'b59f8cf2-93a8-487f-adc5-3e95171ab70d'
   )
   and is_active = true;

-- ── C. Sweep: open terms of already-inactive politicians ───────────
-- 244 rows at authoring time (MB 208, QC 36). An is_active=false
-- politician with an ended_at IS NULL term is definitionally stale —
-- these inflate every "sitting members" count and the enrichment gap
-- queries. Administrative close, NOT a historical end date.

update politician_terms pt
   set ended_at = now()
  from politicians p
 where p.id = pt.politician_id
   and pt.ended_at is null
   and p.is_active = false
   and pt.id <> '3bd1b352-f335-46c2-bdab-0f84d50e4f8b';  -- Proulx handled in A

-- ── D. politician_socials corrections ──────────────────────────────
-- Confirmed name-collisions (documented across 2+ independent runs):
--   Keith Russell 'iamkeithrussell' (IG acf6fdfb + FB 33266807) — UK
--   mental-health podcaster, zero NL/politics content.
--   Rob Weir 'rcweir' (TW 163f99ae) — unrelated ex-IBM professional.
update politician_socials
   set flagged_low_confidence = true, confidence = 0.1
 where id in (
   'acf6fdfb-d3dd-4a0a-80b9-4f513eb371fa',
   '33266807-a565-420a-864d-44583b197450',
   '163f99ae-feeb-43cf-a214-2d1fb154f8f1'
 );

-- Confidence upgrades the insert-only agent couldn't land (blocked by
-- uq_politician_socials_pol_platform_handle; evidence in runbooks):
update politician_socials set confidence = 0.7
 where id = 'cfce3c1c-276c-49a4-97dd-6b47fccaf981';  -- Heather Maahs FB
update politician_socials set confidence = 0.7
 where id = 'f7aed4f3-1947-47a9-bc96-975d1823308a';  -- Sheldon Clare IG
update politician_socials set confidence = 0.9
 where id = '3afc02b9-6747-48c6-80db-2c54ef0dc427';  -- Steve Morissette IG
update politician_socials set confidence = 0.5
 where id = 'ad0de610-e2c3-496f-8da4-49cdf4dd52b9';  -- Rosalyn Bird IG

commit;

-- Post-apply sanity (run separately):
--   SELECT count(*) FROM politician_terms pt JOIN politicians p ON p.id=pt.politician_id
--    WHERE pt.ended_at IS NULL AND p.is_active=false;               -- expect 0
--   SELECT count(*) FROM speeches WHERE politician_id='d1e04c83-315c-44bf-a2ce-77a4fc39bcae';  -- expect 0
--   SELECT refresh_map_views();