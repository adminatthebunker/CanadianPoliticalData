-- One-shot merge of two duplicate politician pairs surfaced by recurring
-- scanner-job failures (2026-07-27). Run once:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < scripts/dedupe_2026_07_roster_dups.sql
--
-- Pair 1 (MB): Jelynn Dela Cruz, sitting MLA for Radisson.
--   keeper ef532873-e13b-416d-987f-bbf163b52dc5  opennorth:manitoba-legislature:jelynn-dela-cruz
--                                                (mb_assembly_slug='delacruz' — matches current roster)
--   loser  84e12b23-da37-4bc9-8c1d-c568ffaf3c95  manitoba-assembly:former-mlas:delacruz-jelynn
--   The loser owns nothing except a degenerate zero-length term
--   (2023-10-03 → 2023-10-03, assembly.mb.ca:former-mlas) which carries no
--   information for a sitting MLA — dropped, not migrated.
--   The dup made mb_mlas._find_existing() ambiguous → insert attempt →
--   unique violation on idx_politicians_mb_assembly_slug, failing
--   ingest-mb-mlas daily.
--
-- Pair 2 (NL): Helen Conway-Ottenheimer, sitting MHA for Harbour Main.
--   keeper 93c3a6f7-77ca-4db2-a07f-afd5ffd994ba  opennorth:newfoundland-labrador-legislature:helen-conway-ottenheimer
--   loser  a3e49272-ca5c-494c-8f5b-d6b2de5086c7  wikipedia:nl-assembly:ottenheimer-helen conway
--   The loser owns 310 speeches (+450 chunks) and one real 50th-GA term
--   (2021-04-15 → 2025-04-23) — both migrated to the keeper. The stub
--   existed because nl_former_mlas' matcher compared the candidate's first
--   name token against the full two-token roster first name ("Helen Conway"),
--   so it never matched anything and re-inserted every run (fixed in code
--   alongside this script).
--
-- Verified before writing this script: neither loser owns socials, offices,
-- committees, changes, bill_sponsors, vote_positions, speech_references,
-- websites, corrections, scrape_jobs, social_posts, or openparliament cache
-- rows — so only speeches / speech_chunks / politician_terms are handled.

begin;

-- ---- Pair 2 (NL): migrate speeches + chunks + the real historical term ----

update speeches
   set politician_id = '93c3a6f7-77ca-4db2-a07f-afd5ffd994ba'
 where politician_id = 'a3e49272-ca5c-494c-8f5b-d6b2de5086c7';

update speech_chunks
   set politician_id = '93c3a6f7-77ca-4db2-a07f-afd5ffd994ba'
 where politician_id = 'a3e49272-ca5c-494c-8f5b-d6b2de5086c7';

update politician_terms
   set politician_id = '93c3a6f7-77ca-4db2-a07f-afd5ffd994ba'
 where politician_id = 'a3e49272-ca5c-494c-8f5b-d6b2de5086c7'
   and not exists (
        select 1 from politician_terms k
         where k.politician_id = '93c3a6f7-77ca-4db2-a07f-afd5ffd994ba'
           and k.office = politician_terms.office
           and k.started_at = politician_terms.started_at
           and k.source = politician_terms.source
   );

-- ---- Pair 1 (MB): nothing to migrate (degenerate term dropped by cascade) ----

-- ---- Delete losers (remaining owned rows cascade / are already migrated) ----

delete from politicians
 where id in ('a3e49272-ca5c-494c-8f5b-d6b2de5086c7',
              '84e12b23-da37-4bc9-8c1d-c568ffaf3c95');

-- ---- Sanity: keepers own the data, losers are gone ----

select 'keeper_nl' as who,
       (select count(*) from speeches
         where politician_id='93c3a6f7-77ca-4db2-a07f-afd5ffd994ba') as speeches,
       (select count(*) from speech_chunks
         where politician_id='93c3a6f7-77ca-4db2-a07f-afd5ffd994ba') as chunks,
       (select count(*) from politician_terms
         where politician_id='93c3a6f7-77ca-4db2-a07f-afd5ffd994ba') as terms
union all
select 'losers_left',
       (select count(*) from politicians
         where id in ('a3e49272-ca5c-494c-8f5b-d6b2de5086c7',
                      '84e12b23-da37-4bc9-8c1d-c568ffaf3c95')),
       0, 0;

commit;
