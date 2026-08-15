-- speeches.meeting_id — first-class FK from municipal caption speeches to
-- their meeting.
--
-- Until now every stage joined speeches to meetings via
-- `source_url LIKE video_url || '%'`. Two problems (2026-08-14 review,
-- fragility B3): '_' is a LIKE wildcard and appears in 14% of YouTube
-- video ids, so a prefix pattern can match ANOTHER meeting's rows (incl.
-- in the reparse DELETE); and the join is an unindexable prefix scan that
-- won't survive the ~1M-speech backfill. The backfill below uses
-- position() (plain substring, no wildcards).

alter table speeches add column if not exists meeting_id uuid references meetings(id) on delete set null;
create index if not exists idx_speeches_meeting on speeches (meeting_id) where meeting_id is not null;

update speeches s
set meeting_id = m.id
from meetings m
where s.meeting_id is null
  and s.source_system like '%-youtube-captions'
  and m.video_url is not null
  and position(m.video_url || '&' in s.source_url) = 1;
