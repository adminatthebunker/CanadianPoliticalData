-- Semantic mind-map: extend the cluster hierarchy from 4 levels to 5.
--
-- Same shape as 0039 / 0040, one more rung. With min_cluster_size=10
-- at L5 on a 4.9M-chunk corpus, L5 lands at ~5,000 micro-clusters
-- (~3-4× more than L4) — enough granularity that the chunk-as-points
-- LOD layer can take over below it without a "where do I look" gap
-- between the deepest cluster and individual quotes.
--
-- DEPENDS ON: 0040 (cluster_id_l4 column + level check including 4).
-- Forward-only — re-running this migration is a no-op via IF NOT
-- EXISTS guards and the defensive DROP/ADD on the level check.
--
-- WHAT THIS DOES NOT DO: backfill cluster_id_l5 onto existing rows.
-- The currently-promoted run was clustered before L5 existed; its
-- cluster_id_l5 stays NULL until the cluster stage reruns. API
-- short-circuits to an empty list when no clusters exist at level=5,
-- so deep-zoom views simply render the chunk layer once chunks are
-- wired up.

alter table speech_clusters
    drop constraint if exists speech_clusters_level_check;
alter table speech_clusters
    add constraint speech_clusters_level_check
    check (level in (1,2,3,4,5));

-- New per-chunk L5 cluster assignment column. Mirrors l1/l2/l3/l4.
alter table speech_chunk_projections
    add column if not exists cluster_id_l5 bigint
        references speech_clusters(id) on delete set null;

create index if not exists idx_chunk_proj_l5
    on speech_chunk_projections(cluster_id_l5)
    where cluster_id_l5 is not null;

-- Per-run L5 cluster count.
alter table projection_runs
    add column if not exists cluster_count_l5 integer;
