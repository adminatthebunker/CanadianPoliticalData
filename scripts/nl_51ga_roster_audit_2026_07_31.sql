-- NL 51st General Assembly roster audit — 2026-07-31
--
-- Completes the roster-hygiene batch (scripts/roster_hygiene_2026_07_31
-- .sql). The official 40 winners of the 2025-10-14 NL general election
-- (PC 21 / Lib 15 / NDP 2 / Ind 2; Elections NL + House of Assembly +
-- CBC, cross-checked; no membership changes through July 2026) were
-- reconciled against our 46 active NL provincial politicians. Six are
-- not in the 51st GA — none appears in any winner list; all six open
-- terms are from the fabricated 2026-04-14 opennorth batch:
--   Gerry Byrne      a32dcb36  term 5e954e2b
--   John Haggie      43e6737f  term fd1afe72
--   Perry Trimper    51395d04  term b8a58359
--   Scott Reid       60b9fccb  term 8d35dc18
--   Siobhan Coady    6b720a01  term 830dfb0d
--   Steve Crocker    7f7cc456  term 48e1b0fb
-- After this script NL reads exactly 40 active politicians = 40 seats.
--
-- Known reconciliation notes (no action needed): DB "James Dinn" is
-- winner Jim Dinn (NDP, St. John's Centre); Eddie Joyce + Paul Lane won
-- as INDEPENDENTS (gov.nl.ca's own results page mislabels them PC —
-- don't let a future parse "fix" their party from that source).
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/nl_51ga_roster_audit_2026_07_31.sql

begin;

update politician_terms
   set ended_at = started_at        -- fabricated rows: zero-length void
 where ended_at is null
   and id in (
     '5e954e2b-4efe-4a7e-a38d-e97b67781c59',
     'fd1afe72-972a-41db-ab34-6329575b70e9',
     'b8a58359-3797-4fff-80f0-be7a03d38fb6',
     '8d35dc18-8230-4811-99b0-e35281ecb96d',
     '830dfb0d-c29a-4f6a-9327-7b1990bdb548',
     '48e1b0fb-6fb2-4bed-8123-ffad1f0549c0'
   );

update politicians
   set is_active = false
 where id in (
     'a32dcb36-b906-4924-84e7-2b5d8435ea15',  -- Gerry Byrne
     '43e6737f-e7c6-438f-af7f-2ac3d9f79e59',  -- John Haggie
     '51395d04-95ab-4c77-b81e-6e7bc540cc63',  -- Perry Trimper
     '60b9fccb-6f0b-41db-a2e1-f8a7c0d62482',  -- Scott Reid
     '6b720a01-175f-4b3a-be3d-b6773e96015d',  -- Siobhan Coady
     '7f7cc456-a3de-4f04-af03-6f94f2f39076'   -- Steve Crocker
   )
   and is_active = true;

commit;