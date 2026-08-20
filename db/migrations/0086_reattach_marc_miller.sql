-- 0086 — Re-attach Marc Miller after the mirror refresh detached him.
--
-- `0085` re-attached provincial members by slug but not federal ones, because
-- federal `constituency_id`s are keyed on FED_NUM rather than a name slug — so
-- there is no slug to join on. Every other federal member was recovered by the
-- prefix swap; Marc Miller was not, because he is the one MP whose district
-- (24077, Ville-Marie—Le Sud-Ouest—Île-des-Sœurs) was absent from the Open North
-- mirror entirely, so the refresh had no mirror id to give him and left NULL.
--
-- ⚠ Attached by FED_NUM, not by name: Elections Canada writes `Île-des-Soeurs`
-- (oe digraph) and our roster carries `Île-des-Sœurs` (œ ligature, U+0153).
-- Those are different strings and a name join silently misses — the same reason
-- 0072 attached him this way in the first place.
--
-- Forward-only. Apply with:
--   docker exec -i sw-db psql -U sw -d sovereignwatch -v ON_ERROR_STOP=1 \
--     < db/migrations/0086_reattach_marc_miller.sql

BEGIN;

UPDATE politicians
   SET constituency_id = 'federal-electoral-districts/24077', updated_at = now()
 WHERE level = 'federal' AND is_active AND elected_office = 'MP'
   AND constituency_id IS NULL
   AND constituency_name LIKE 'Ville-Marie%';

DO $$
DECLARE unattached int;
BEGIN
    SELECT count(*) INTO unattached FROM politicians
     WHERE level='federal' AND is_active AND elected_office='MP'
       AND constituency_id IS NULL;
    IF unattached <> 0 THEN
        RAISE EXCEPTION '% MPs still unattached', unattached;
    END IF;
    RAISE NOTICE 'federal: 343 of 343 MPs attached';
END $$;

COMMIT;
