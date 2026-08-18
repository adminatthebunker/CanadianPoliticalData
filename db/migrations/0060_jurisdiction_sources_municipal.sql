-- 0060_jurisdiction_sources_municipal.sql
--
-- Let the coverage dashboard describe municipalities, not just the 14
-- legislatures it was seeded with in 0019.
--
-- Shape follows load-bearing convention #2 (discriminated tables, not
-- per-jurisdiction tables): municipalities are rows in the SAME
-- jurisdiction_sources table, discriminated by `level` and pointed at
-- their province by `parent_jurisdiction`. No `municipal_sources` table.
--
-- `municipality_slug` is the join key back to meetings.municipality_slug.
-- It exists because speeches carry no city column — the only path from a
-- speech to a city is speeches.meeting_id -> meetings.municipality_slug
-- (see 0059) — so the stats refresher needs the slug to count anything.
--
-- Seeded with the two cities that actually have a council-meeting
-- pipeline. Councillor rosters exist for ~90 more municipalities via
-- Open North, but those are roster-only (no meetings, no transcripts)
-- and are deliberately NOT surfaced here; a row in this table asserts
-- "we ingest this council's proceedings".

begin;

alter table jurisdiction_sources
  add column if not exists level text not null default 'provincial',
  add column if not exists parent_jurisdiction text,
  add column if not exists municipality_slug text;

-- Backfill the discriminator for the rows 0019 seeded.
update jurisdiction_sources set level = 'federal' where jurisdiction = 'federal';

alter table jurisdiction_sources
  drop constraint if exists jurisdiction_sources_level_check;
alter table jurisdiction_sources
  add constraint jurisdiction_sources_level_check
  check (level in ('federal', 'provincial', 'municipal'));

-- A municipal row must name both its parent and its slug; a
-- federal/provincial row must have neither. Enforced rather than
-- documented because the API's parent-child ordering and the stats
-- refresher's join both silently produce wrong output on a half-filled
-- row (orphaned child rows sort to the end; a null slug counts zero).
alter table jurisdiction_sources
  drop constraint if exists jurisdiction_sources_municipal_shape_check;
alter table jurisdiction_sources
  add constraint jurisdiction_sources_municipal_shape_check
  check (
    (level = 'municipal'
       and parent_jurisdiction is not null
       and municipality_slug is not null)
    or
    (level <> 'municipal'
       and parent_jurisdiction is null
       and municipality_slug is null)
  );

alter table jurisdiction_sources
  drop constraint if exists jurisdiction_sources_parent_fkey;
alter table jurisdiction_sources
  add constraint jurisdiction_sources_parent_fkey
  foreign key (parent_jurisdiction) references jurisdiction_sources(jurisdiction)
  on delete cascade;

create index if not exists idx_jurisdiction_sources_parent
  on jurisdiction_sources (parent_jurisdiction)
  where parent_jurisdiction is not null;

-- ── Seed: cities with a real council-proceedings pipeline ────────────
--
-- Statuses below are opening values only. refresh-coverage-stats
-- re-derives bills/hansard/votes/committees from live row counts on
-- every run, exactly as it does for the legislatures.
--
-- `seats` is council size including the mayor (Edmonton 12 councillors
-- + mayor; Calgary 14 councillors + mayor).

insert into jurisdiction_sources (
  jurisdiction, legislature_name, seats, level,
  parent_jurisdiction, municipality_slug,
  bills_status, hansard_status, votes_status, committees_status,
  hansard_difficulty, notes, source_urls
) values (
  'AB-edmonton', 'Edmonton City Council', 13, 'municipal',
  'AB', 'edmonton',
  'none', 'live', 'none', 'live',
  3,
  'Council and committee proceedings transcribed from the City''s published meeting captions, 2022 to today. Bylaws and recorded votes are not ingested yet.',
  '{"meetings": "https://pub-edmonton.escribemeetings.com/"}'::jsonb
), (
  'AB-calgary', 'Calgary City Council', 15, 'municipal',
  'AB', 'calgary',
  'none', 'none', 'none', 'none',
  4,
  'Agendas and minutes are published through eScribe, which does not expose transcripts to server-side callers, and the City runs no captioned video channel. Scaffolded but parked pending a workable source.',
  '{"meetings": "https://pub-calgary.escribemeetings.com/"}'::jsonb
)
on conflict (jurisdiction) do nothing;

commit;
