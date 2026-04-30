-- Semantic mind-map: extend the cluster hierarchy from 3 levels to 4.
--
-- Same shape as 0039, just one rung deeper. With min_cluster_size=20
-- on the 3D coords, L4 lands roughly an order of magnitude finer than
-- L3 (~3-4 L4 children per L3 parent at production scale).
--
-- DEPENDS ON: 0039 (speech_clusters / speech_chunk_projections /
-- projection_runs). Forward-only — re-running this migration is a
-- no-op via the IF NOT EXISTS guards on the column adds and the
-- defensive DROP/ADD on the CHECK constraint.
--
-- WHAT THIS DOES NOT DO: backfill cluster_id_l4 onto existing rows.
-- The current promoted run was clustered before L4 existed, so its
-- cluster_id_l4 stays NULL until the operator reruns the cluster
-- stage (or runs a fresh fit/cluster/label/promote cycle). The API
-- already short-circuits to an empty cluster list when no clusters
-- exist at the requested level, so the L4 view simply renders empty
-- on the legacy run — no breakage.

-- Widen the level check on speech_clusters to allow level=4.
-- The constraint name is implicit (Postgres synthesises
-- speech_clusters_level_check); we drop by name then re-add.
alter table speech_clusters
    drop constraint if exists speech_clusters_level_check;
alter table speech_clusters
    add constraint speech_clusters_level_check
    check (level in (1,2,3,4));

-- New per-chunk L4 cluster assignment column. Same shape as the
-- existing l1/l2/l3 columns — NULL means HDBSCAN noise (or an
-- unclustered legacy run).
alter table speech_chunk_projections
    add column if not exists cluster_id_l4 bigint
        references speech_clusters(id) on delete set null;

create index if not exists idx_chunk_proj_l4
    on speech_chunk_projections(cluster_id_l4)
    where cluster_id_l4 is not null;

-- Per-run L4 cluster count (immutable once populated by the
-- cluster stage). Mirrors the l1/l2/l3 counterparts.
alter table projection_runs
    add column if not exists cluster_count_l4 integer;
