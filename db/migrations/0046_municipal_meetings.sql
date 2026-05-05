-- Municipal layer phase 1 — meetings table + bills.meeting_id FK + seed sessions.
--
-- First migration of the municipal-data workstream. Calgary + Edmonton are
-- the wedge: both run their council agendas on the eScribe SaaS
-- (pub-{calgary,edmonton}.escribemeetings.com), which exposes a JSON
-- meeting-list endpoint at /MeetingsContent.aspx/PastMeetings.
--
-- Decisions baked into the schema (see /home/bunker-admin/.claude/plans/
-- federated-churning-swan.md and docs/research/cities/overview.md):
--   - motions and bylaws overload the existing `bills` table with
--     level='municipal' + bill_type IN ('motion','bylaw'). No new tables
--     for that layer.
--   - one synthesized legislative_sessions row per council term per city
--     (bills.session_id is NOT NULL; a meeting → session lookup uses
--     started_at falling within [start_date, end_date]).
--   - new `meetings` table is the only municipal-only structure; it's a
--     thin parent for motions/bylaws and the join target for YouTube-caption
--     speech rows (via meetings.video_url + speeches.source_url anchoring).
--
-- Verified pre-write (2026-05-05):
--   - bills.level has NO check constraint (live DB inspection); 'municipal'
--     accepted without altering bills.
--   - legislative_sessions.level has NO check constraint either.
--   - speeches.level and votes.level CHECKs already include 'municipal'.
--   - touch_updated_at() function exists (defined in earlier migrations).
--
-- Forward-only. Re-running is a no-op via IF NOT EXISTS guards and
-- ON CONFLICT DO NOTHING on the seed inserts.

-- ─────────────────────────────────────────────────────────────────────
-- meetings — the council-meeting forum.
--
-- Natural key: (source_system, source_meeting_id) — eScribe's GUID stays
-- stable across re-fetches. session_id resolves to the synthesized
-- council-term row in legislative_sessions; the resolver is in
-- escribe_ingest.py (not a SQL function, since the data flow always knows
-- the term up-front from the meeting date).
-- ─────────────────────────────────────────────────────────────────────
create table if not exists meetings (
    id                 uuid primary key default gen_random_uuid(),
    session_id         uuid not null references legislative_sessions(id) on delete cascade,
    level              text not null default 'municipal',
    province_territory text not null,                 -- 'AB' for both Calgary and Edmonton
    municipality_slug  text not null,                 -- 'calgary' | 'edmonton'
    body_name          text not null,                 -- 'Council' | 'SPC on Community Services' | ...
    body_type          text not null default 'council',
                                                      -- 'council' | 'committee' | 'committee_of_the_whole'
    started_at         timestamptz,
    ended_at           timestamptz,
    agenda_url         text,
    minutes_url        text,
    video_url          text,                          -- YouTube URL once Stage 5 runs
    source_system      text not null,                 -- 'calgary-escribemeetings' | 'edmonton-escribemeetings'
    source_meeting_id  text not null,                 -- eScribe GUID/ID
    raw_html           text,                          -- per-meeting HTML cache
    raw_minutes_html   text,                          -- minutes HTML cache (when distinct)
    raw                jsonb not null default '{}'::jsonb,
    fetched_at         timestamptz,
    fetch_error        text,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    unique (source_system, source_meeting_id)
);

create index if not exists idx_meetings_municipality on meetings (municipality_slug, started_at desc);
create index if not exists idx_meetings_session      on meetings (session_id);
create index if not exists idx_meetings_unfetched    on meetings (id) where raw_html is null;

drop trigger if exists trg_meetings_touch on meetings;
create trigger trg_meetings_touch before update on meetings
    for each row execute function touch_updated_at();

-- ─────────────────────────────────────────────────────────────────────
-- bills.meeting_id — every municipal motion/bylaw originates at a meeting.
-- Nullable because federal/provincial bills don't have a meeting concept.
-- ─────────────────────────────────────────────────────────────────────
alter table bills add column if not exists meeting_id uuid references meetings(id) on delete set null;
create index if not exists idx_bills_meeting on bills (meeting_id) where meeting_id is not null;

-- ─────────────────────────────────────────────────────────────────────
-- Seed legislative_sessions for current + previous council terms.
--
-- parliament_number convention for municipal: <CC><YY> where CC = city
-- code (15 = Calgary, 25 = Edmonton) and YY = term-start year. Avoids
-- collisions with provincial parliament numbers (which are small ints
-- starting at 1) and gives readable IDs (1521 = Calgary 2021).
--
-- Edmonton dates: city's 2021 election was 2021-10-18 (same day as
-- Calgary's). Both cities held subsequent general elections 2025-10-20.
-- ─────────────────────────────────────────────────────────────────────
insert into legislative_sessions
    (level, province_territory, parliament_number, session_number, name, start_date, end_date, source_system)
values
    ('municipal', 'AB', 1521, 1, 'Calgary 2021–2025 Council Term',  '2021-10-18', '2025-10-19', 'calgary-escribemeetings'),
    ('municipal', 'AB', 1525, 1, 'Calgary 2025–2029 Council Term',  '2025-10-20', null,         'calgary-escribemeetings'),
    ('municipal', 'AB', 2521, 1, 'Edmonton 2021–2025 Council Term', '2021-10-18', '2025-10-19', 'edmonton-escribemeetings'),
    ('municipal', 'AB', 2525, 1, 'Edmonton 2025–2029 Council Term', '2025-10-20', null,         'edmonton-escribemeetings')
on conflict (level, province_territory, parliament_number, session_number) do nothing;
