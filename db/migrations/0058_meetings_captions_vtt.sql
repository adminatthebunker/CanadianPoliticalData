-- Move the canonical caption VTT off the speeches delete path.
--
-- Until now the only copy of a meeting's VTT lived in speeches.raw_html on
-- the sequence=1 row. reparse-meeting-captions deletes all of a meeting's
-- speeches and re-inserts them row-by-row (autocommit), so a kill between
-- the DELETE and the seq-1 INSERT permanently lost the VTT and forced a
-- YouTube re-fetch (2026-08-14 pipeline review, fragility B2). The VTT now
-- lives on the meeting row, parallel to raw_minutes_html.
--
-- Backfill note: source_url = video_url || '&t=<seconds>', so prefix
-- matching uses position() (plain substring) — LIKE would treat the '_' in
-- YouTube video ids as a wildcard (92/654 Edmonton URLs contain one).

alter table meetings add column if not exists raw_captions_vtt text;

update meetings m
set raw_captions_vtt = s.raw_html
from speeches s
where m.raw_captions_vtt is null
  and m.video_url is not null
  and s.sequence = 1
  and s.raw_html is not null
  and s.source_system like '%-youtube-captions'
  and position(m.video_url || '&' in s.source_url) = 1;
