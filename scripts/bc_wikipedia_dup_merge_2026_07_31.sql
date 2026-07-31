-- BC Wikipedia-roster duplicate merge — 2026-07-31
--
-- The P35-38 gap-fill (bc_former_mlas, hardened matcher) still created
-- six name-variant duplicates the nickname/initial fallbacks can't
-- reach (parenthesized nicknames "Armando (Sandy)", "N.L. (Bill)",
-- honorific prefix "Rev.", MacPhail/McPhail spelling drift, and a
-- particle-surname parse bug that stores "de Jong" as last_name
-- "Jong"). Plus one pre-existing duplicate of the same vintage from
-- the original P29-34 runs (Harry H. De Jong).
--
-- Merge: move each duplicate's terms to the canonical row unless the
-- canonical already has an overlapping provincial term (LIMS coverage),
-- then delete the duplicate.
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/bc_wikipedia_dup_merge_2026_07_31.sql

begin;

create temp table merge_map (dup_id uuid, canon_id uuid);
insert into merge_map
select d.id, c.id
from (values
    ('wikipedia:bc-mla:Joy_MacPhail',                      'Joy MacPhail'),
    ('wikipedia:bc-mla:Mike_de_Jong',                      'Michael de Jong'),
    ('wikipedia:bc-mla:Bill_Barlee',                       'Bill Barlee'),
    ('wikipedia:bc-mla:Richard_Lee_(Canadian_politician)', 'Richard T. Lee'),
    ('wikipedia:bc-mla:Sandy_Santori',                     'Armando (Sandy) Santori'),
    ('wikipedia:bc-mla:Val_Anderson',                      'Rev. Val Anderson')
) v(dup_source, canon_name)
join politicians d on d.source_id = v.dup_source
    and d.province_territory = 'BC' and d.created_at::date = current_date
join politicians c on c.name = v.canon_name
    and c.province_territory = 'BC' and c.level = 'provincial'
    and c.id <> d.id;

-- Pre-existing duplicate pair (last_name mis-split as 'Jong').
insert into merge_map
select d.id, c.id
from politicians d, politicians c
where d.name = 'Harry H. De Jong' and d.province_territory = 'BC'
  and d.lims_member_id is null
  and c.name = 'Harry De Jong' and c.province_territory = 'BC'
  and c.lims_member_id = 296;

-- Terms: drop those overlapping existing canonical coverage; move the rest.
delete from politician_terms t
 using merge_map m
 where t.politician_id = m.dup_id
   and exists (
     select 1 from politician_terms ct
      where ct.politician_id = m.canon_id
        and ct.level = 'provincial'
        and ct.started_at < coalesce(t.ended_at, 'infinity'::timestamptz)
        and coalesce(ct.ended_at, 'infinity'::timestamptz) > t.started_at
   );

update politician_terms t
   set politician_id = m.canon_id
  from merge_map m
 where t.politician_id = m.dup_id;

-- Re-point / clear any other references, then delete the duplicates.
update vote_positions set politician_id = null
 where politician_id in (select dup_id from merge_map);
update speeches s set politician_id = m.canon_id
  from merge_map m where s.politician_id = m.dup_id;
delete from politician_committees
 where politician_id in (select dup_id from merge_map);
delete from politician_socials
 where politician_id in (select dup_id from merge_map);
delete from politician_offices
 where politician_id in (select dup_id from merge_map);
delete from politicians where id in (select dup_id from merge_map);

commit;