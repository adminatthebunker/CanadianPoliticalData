-- Eric/Éric Girard row-identity reconciliation — 2026-07-31
--
-- Two different sitting CAQ MNAs share the name: Eric Girard (Groulx,
-- ministre des Finances, assnat id 17929) and Éric Girard
-- (Lac-Saint-Jean, ministre délégué au Développement économique
-- régional, assnat id 17957). Both ids verified live against
-- assnat.qc.ca/fr/deputes/ this date. Our DB had:
--   bdf62884  labeled Groulx, MFQ+Groulx handles, 127 speeches, NO assnat id
--   b6112064  labeled Lac-Saint-Jean, LSJ handles, 1811 speeches,
--             WRONGLY carrying 17929 (the Groulx id)
--   449b99da  orphan dup: no terms, 0 speeches, carrying 17957 + a
--             contaminated LSJ facebook handle
-- Wikidata-sourced 'EricGirardLacSaintJean' facebook rows were smeared
-- across all three (socials-agent items 4/13/24, 2026-07).
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/girard_row_reconciliation_2026_07_31.sql

begin;

-- Free both ids first (qc_assnat_id may be uniquely indexed).
update politicians set qc_assnat_id = null
 where id = '449b99da-c2b4-49a6-b033-bc31af0df856' and qc_assnat_id = 17957;
update politicians set qc_assnat_id = null
 where id = 'b6112064-8d0a-4ecd-b199-b256a514e332' and qc_assnat_id = 17929;

-- Assign each id to the row that actually holds that person's history.
update politicians set qc_assnat_id = 17929
 where id = 'bdf62884-39a0-45fa-b09f-5e6387eca5dc';   -- Groulx / Finance
update politicians set qc_assnat_id = 17957
 where id = 'b6112064-8d0a-4ecd-b199-b256a514e332';   -- Lac-Saint-Jean

-- De-smear the LSJ facebook handle: it belongs only to the LSJ row.
delete from politician_socials
 where lower(handle) = 'ericgirardlacsaintjean' and platform = 'facebook'
   and politician_id in (
     'bdf62884-39a0-45fa-b09f-5e6387eca5dc',
     '449b99da-c2b4-49a6-b033-bc31af0df856'
   );

-- 'sharer' facebook handles are share-button scraper artifacts, not
-- accounts — drop them on these three rows while we're here. (The
-- pattern exists elsewhere too; broader cleanup is a separate pass.)
delete from politician_socials
 where platform = 'facebook' and lower(handle) = 'sharer'
   and politician_id in (
     'bdf62884-39a0-45fa-b09f-5e6387eca5dc',
     '449b99da-c2b4-49a6-b033-bc31af0df856',
     'b6112064-8d0a-4ecd-b199-b256a514e332'
   );

-- Deactivate the orphan duplicate (no terms, no speeches, no identity
-- left). A future merge into b6112064 is possible but there's nothing
-- of substance to migrate.
update politicians set is_active = false
 where id = '449b99da-c2b4-49a6-b033-bc31af0df856';

commit;

-- Post-apply sanity (run separately):
--   SELECT id, name, qc_assnat_id, is_active FROM politicians
--    WHERE id::text LIKE 'b6112064%' OR id::text LIKE 'bdf62884%' OR id::text LIKE '449b99da%';