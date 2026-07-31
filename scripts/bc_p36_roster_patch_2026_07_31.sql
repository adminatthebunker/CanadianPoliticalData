-- BC 36th-Parliament roster patch — 2026-07-31
--
-- The V&P divisions ingest (commit 4f543f5) surfaced four P36 roster
-- gaps that LIMS itself cannot fill: `allMemberParliaments` carries
-- only P35 edges for members 302/306/162 (verified live 2026-07-31),
-- and Paul Reitsma is absent from LIMS `allMembers` entirely. Dates
-- below were independently verified via Wikipedia/CBC/Elections BC:
--
--   Fred Gingell (Delta South, BC Liberal)  — served P36 until his
--     death in office 1999-07-06.
--   Wilf Hurd (Surrey-White Rock, BC Liberal) — resigned 1997 to
--     contest the 1997-06-02 federal election (Gordie Hogg won the
--     1997-09-15 by-election); end date approximated to the federal
--     election day.
--   Gretchen Mann Brewin (Victoria-Beacon Hill, NDP) — served the
--     full P36 (1991-2001).
--   Paul Reitsma (Parksville-Qualicum, BC Liberal) — P35 + P36;
--     resigned 1998-06-23, one day before his recall petition was
--     verified (the "fax fraud" scandal). Judith Reid won the
--     1998-12-14 by-election for the seat.
--
-- BONUS FIX: Judith Reid's first term start was 1996-06-26 — wrong;
-- she ENTERED via that 1998-12-14 by-election. Correcting it makes
-- every bare "Reid" in 1996-1998 V&P divisions unambiguously Linda
-- Reid (both Reids sat only from 1998-12-14 onward).
--
-- Term-row conventions match the lims parliament rows (office='MLA',
-- P36 start 1996-06-26); source tag 'bc-p36-roster-patch' for
-- batch-level auditability.
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/bc_p36_roster_patch_2026_07_31.sql

begin;

-- P36 terms for the three existing politicians.
insert into politician_terms
    (politician_id, office, party, level, province_territory,
     constituency_id, started_at, ended_at, source)
values
    ((select id from politicians where province_territory='BC' and name='Fred Gingell'),
     'MLA', 'BC Liberal', 'provincial', 'BC',
     'bc-electoral-districts/delta-south',
     '1996-06-26T00:00:00Z', '1999-07-06T23:59:00Z', 'bc-p36-roster-patch'),
    ((select id from politicians where province_territory='BC' and name='Wilf Hurd'),
     'MLA', 'BC Liberal', 'provincial', 'BC',
     'bc-electoral-districts/surrey-white-rock',
     '1996-06-26T00:00:00Z', '1997-06-02T23:59:00Z', 'bc-p36-roster-patch'),
    ((select id from politicians where province_territory='BC' and name='Gretchen Mann Brewin'),
     'MLA', 'New Democratic Party of BC', 'provincial', 'BC',
     'bc-electoral-districts/victoria-beacon-hill',
     '1996-06-26T00:00:00Z', '2001-04-18T23:59:00Z', 'bc-p36-roster-patch');

-- Paul Reitsma: new politician row (absent from LIMS) + P35/P36 terms.
insert into politicians
    (source_id, name, first_name, last_name, level, province_territory,
     elected_office, social_urls, extras, is_active)
values
    ('bc-p36-roster-patch:paul-reitsma', 'Paul Reitsma', 'Paul', 'Reitsma',
     'provincial', 'BC', 'MLA', '{}'::jsonb, '{}'::jsonb, false)
on conflict do nothing;

insert into politician_terms
    (politician_id, office, party, level, province_territory,
     constituency_id, started_at, ended_at, source)
values
    ((select id from politicians where source_id='bc-p36-roster-patch:paul-reitsma'),
     'MLA', 'BC Liberal', 'provincial', 'BC',
     'bc-electoral-districts/parksville-qualicum',
     '1992-03-17T00:00:00Z', '1996-04-30T23:59:00Z', 'bc-p36-roster-patch'),
    ((select id from politicians where source_id='bc-p36-roster-patch:paul-reitsma'),
     'MLA', 'BC Liberal', 'provincial', 'BC',
     'bc-electoral-districts/parksville-qualicum',
     '1996-06-26T00:00:00Z', '1998-06-23T23:59:00Z', 'bc-p36-roster-patch');

-- Judith Reid entered via the 1998-12-14 Parksville-Qualicum
-- by-election, not at the 1996 general.
update politician_terms
   set started_at = '1998-12-14T00:00:00Z'
 where id = 'efb8c2ee-3e95-4c6a-97aa-d5d030400a81'
   and started_at::date = '1996-06-26';

commit;

-- Post-apply: re-run `ingest-bc-vp-votes --parliament 36` — positions
-- are delete-then-insert per vote, so resolution re-runs cleanly.