-- SK duplicate-politician group merge — 2026-07-31 (v2)
--
-- The cross-jurisdiction duplicate audit enumerated SK's documented
-- duplicate-politician problem, and the v1 pair-merge attempt revealed
-- its true shape: returning members exist as TRIPLES — a
-- `legassembly.sk.ca:29L-speaker-index` row, a `:30L-speaker-index`
-- row (usually "Hon."-prefixed, is_active, holding the speeches), and
-- an `opennorth:saskatchewan-legislature` orphan (holding the open
-- politician_terms row). Split-brain: terms on one row, speeches on
-- another.
--
-- v2 groups SK provincial politicians by Hon.-stripped normalized name
-- and merges each group into ONE canonical, ranked: is_active first,
-- then 30L-index source, then speech count. SAFEGUARD: groups where
-- two rows BOTH hold >100 speeches are skipped and reported — that
-- shape could be two real same-named people (the Cooke rule).
--
-- The Open North source_id moves onto the canonical so the daily
-- opennorth ingest converges on it instead of re-creating the orphan.
--
-- Apply: docker exec -i sw-db psql -U sw -d sovereignwatch \
--          -v ON_ERROR_STOP=1 < scripts/sk_hon_dup_merge_2026_07_31.sql

begin;

create temp table sk_rows as
select p.id,
       lower(regexp_replace(regexp_replace(p.name, '^Hon\.\s+', ''), '\s+', ' ', 'g')) as norm_name,
       p.source_id, p.is_active,
       (p.source_id like 'legassembly.sk.ca:30L%')::int as is_30l,
       (p.source_id like 'opennorth:%')::int as is_on,
       (select count(*) from speeches s where s.politician_id = p.id) as speeches
  from politicians p
 where p.province_territory = 'SK' and p.level = 'provincial';

-- Groups with a two-heavy-speech-rows shape: skip + report (possible
-- genuinely distinct people).
create temp table sk_skip as
select norm_name from sk_rows
 group by norm_name
having count(*) > 1
   and count(*) filter (where speeches > 100) > 1;

select 'SKIPPED (review manually):' as note, norm_name from sk_skip;

create temp table sk_groups as
select norm_name,
       (array_agg(id order by is_active desc, is_30l desc, speeches desc))[1] as canon_id,
       array_agg(id) as all_ids,
       max(source_id) filter (where is_on = 1) as on_source
  from sk_rows
 where norm_name not in (select norm_name from sk_skip)
 group by norm_name
having count(*) > 1;

create temp table skm as
select unnest(all_ids) as dup_id, canon_id, on_source
  from sk_groups;
delete from skm where dup_id = canon_id;

select count(*) as rows_to_merge from skm;

-- Free source_ids held by dups first (unique constraint).
update politicians set source_id = id::text || ':merged'
 where id in (select dup_id from skm);

update politician_terms t set politician_id = skm.canon_id
  from skm where t.politician_id = skm.dup_id;
update speeches s set politician_id = skm.canon_id
  from skm where s.politician_id = skm.dup_id;
update vote_positions vp set politician_id = skm.canon_id
  from skm where vp.politician_id = skm.dup_id;
update politician_socials ps set politician_id = skm.canon_id
  from skm where ps.politician_id = skm.dup_id
  and not exists (select 1 from politician_socials x
                   where x.politician_id = skm.canon_id
                     and x.platform = ps.platform
                     and lower(x.handle) = lower(ps.handle));
delete from politician_socials where politician_id in (select dup_id from skm);
delete from politician_committees where politician_id in (select dup_id from skm);
delete from politician_offices where politician_id in (select dup_id from skm);

-- Converge the opennorth ingest on the canonical (skip canonicals that
-- already carry an opennorth id).
update politicians c set source_id = g.on_source
  from sk_groups g
 where c.id = g.canon_id and g.on_source is not null
   and c.source_id not like 'opennorth:%';

delete from politicians where id in (select dup_id from skm);

commit;