"""speech_chunks.embedding -> 3D/2D coordinates + cluster hierarchy.

Powers the /semantic-map page. Three idempotent stages, each its own
function so the operator can re-run cheaply if one stage fails:

  fit     : UMAP-3D + UMAP-2D on a stratified sample of speech_chunks,
            then transform the rest in batches. Writes
            speech_chunk_projections rows (cluster_ids NULL).
  cluster : HDBSCAN at three min_cluster_size levels on the 3D coords.
            Writes speech_clusters rows + updates projections.
  label   : Per-cluster TF-IDF over chunk text (en + fr stopwords);
            label = top-3 terms joined; top_terms = full ranked list.
            Picks 15 representative chunks closest to centroid.
  promote : Transactional flip of projection_runs.is_current. The API
            reads the single is_current=true row each request, so the
            swap takes effect on the next API request.
  gc      : Drop superseded runs older than --max-age-days. Cascades
            kill the corresponding clusters + projections.

Memory discipline:

  - 3.4M chunks * 1024 dims * float32 = ~14 GB total. We never load
    the full corpus into RAM. Fit on a 500k stratified sample
    (~2 GB), then transform the rest in 50k batches.
  - HDBSCAN runs on the 3D coords (3.4M * 3 * 4 = ~40 MB), not the
    1024-d originals. Conventionally just as good and 1000x faster.

asyncio note:
  UMAP / HDBSCAN / sklearn calls are CPU-bound and blocking. We dispatch
  them via asyncio.to_thread so they don't stall the asyncpg pool's
  event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from ..db import Database

log = logging.getLogger(__name__)


# ─── Tunables ──────────────────────────────────────────────────────

UMAP_N_NEIGHBORS = 30
UMAP_MIN_DIST = 0.05
UMAP_RANDOM_STATE = 42
DEFAULT_SAMPLE_SIZE = 500_000
DEFAULT_TRANSFORM_BATCH = 50_000

# HDBSCAN min_cluster_size at each level. Roughly: ~30 / ~200 / ~1500 /
# ~6000 clusters at 3.4M chunks. Tunable per run via --params at the CLI.
# L4 (mcs=20) yields ~3-4 children per L3 cluster on average — fine
# enough to be worth drilling into without exploding the cluster count
# beyond what the labelling stage can chew through.
HDBSCAN_MIN_SIZES = (900, 300, 100, 30, 10)

# Fitting HDBSCAN on the full corpus OOMs the box at ~5M points: the MST
# construction working set bloats past available RAM. Instead, we fit on
# a uniform random sample of this size, then assign every remaining point
# to its nearest sample-cluster centroid via a KDTree query on the 3D
# coords. A sample of 500k preserves the density landscape (HDBSCAN's
# selling point over KMeans) while keeping peak memory under ~6 GB.
HDBSCAN_SAMPLE_SIZE = 500_000
HDBSCAN_SAMPLE_SEED = 42  # deterministic so re-runs land identical labels.

# TF-IDF labelling.
LABEL_TOP_N = 3            # words joined to form the label
LABEL_TOP_TERMS_KEEP = 20  # full ranked list persisted as JSONB
LABEL_TOP_CHUNK_IDS = 15   # representative chunks for the drawer
LABEL_MAX_FEATURES = 5000
LABEL_NGRAM = (1, 2)
LABEL_MIN_DF = 2
LABEL_MAX_DF = 0.6
LABEL_MAX_DOCS_PER_CLUSTER = 20_000  # cap TF-IDF matrix size for huge clusters


# Stopwords. sklearn ships English; French is a hand-rolled list of
# the top function words / common adverbs. Hansard is bilingual and
# English-only stops would leave terms like "le", "des", "qui" in the
# top-N.
FRENCH_STOPWORDS = {
    "alors", "au", "aux", "aussi", "autre", "avant", "avec", "avoir",
    "bon", "car", "ce", "cela", "ces", "ceux", "cet", "cette", "ci",
    "comme", "comment", "dans", "des", "du", "dedans", "dehors",
    "depuis", "deux", "devrait", "doit", "donc", "dos", "droite",
    "début", "elle", "elles", "en", "encore", "essai", "est", "et",
    "eu", "fait", "faites", "fois", "font", "hors", "ici", "il", "ils",
    "je", "juste", "la", "le", "les", "leur", "là", "ma", "maintenant",
    "mais", "mes", "mine", "moins", "mon", "mot", "même", "ni", "nommés",
    "notre", "nous", "ou", "où", "par", "parce", "pas", "peu", "peut",
    "plupart", "pour", "pourquoi", "quand", "que", "quel", "quelle",
    "quelles", "quels", "qui", "sa", "sans", "ses", "seulement", "si",
    "sien", "son", "sont", "sous", "soyez", "sujet", "sur", "ta", "tandis",
    "tellement", "tels", "tes", "ton", "tous", "tout", "trop", "très",
    "tu", "voient", "vont", "votre", "vous", "vu", "ça", "étaient",
    "état", "étions", "été", "être",
    # Hansard-specific noise: speaker / chamber boilerplate.
    "monsieur", "madame", "président", "présidente", "député", "députée",
    "honorable", "ministre", "merci", "membres", "chambre",
}


# ─── Module-level state-of-the-art messages ────────────────────────


@dataclass
class FitStats:
    chunks_seen: int = 0
    sample_size: int = 0
    fit_seconds_3d: float = 0.0
    fit_seconds_2d: float = 0.0
    transform_seconds: float = 0.0
    rows_written: int = 0


@dataclass
class ClusterStats:
    level_counts: dict[int, int] = field(default_factory=dict)
    noise_per_level: dict[int, int] = field(default_factory=dict)
    cluster_seconds: float = 0.0


@dataclass
class LabelStats:
    clusters_labelled: int = 0
    chunks_read: int = 0
    seconds: float = 0.0


# ─── pgvector parsing ──────────────────────────────────────────────

_VEC_TOKEN = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _parse_vector(text_repr: str) -> np.ndarray:
    """Parse pgvector textual form '[0.1,0.2,...]' to float32 np.ndarray.

    asyncpg has no native vector codec. We select `embedding::text` and
    parse here. ~3 us per vector at 1024 dims, dwarfed by transform cost.
    """
    return np.fromstring(text_repr.strip("[]"), sep=",", dtype=np.float32)


# ─── Run lifecycle ─────────────────────────────────────────────────


async def create_run(db: Database, params: dict[str, Any]) -> str:
    """Insert a new projection_runs row in 'running' state. Returns run_id."""
    row = await db.fetchrow(
        """
        INSERT INTO projection_runs (status, params)
        VALUES ('running', $1::jsonb)
        RETURNING id::text
        """,
        json.dumps(params),
    )
    return row["id"]


async def find_latest_running_run(db: Database) -> Optional[str]:
    row = await db.fetchrow(
        """
        SELECT id::text FROM projection_runs
        WHERE status = 'running'
        ORDER BY started_at DESC LIMIT 1
        """
    )
    return row["id"] if row else None


async def mark_run_status(
    db: Database, run_id: str, status: str, *,
    chunk_count: Optional[int] = None,
    cluster_counts: Optional[tuple[int, ...]] = None,
    notes: Optional[str] = None,
) -> None:
    sets = ["status = $2"]
    args: list[Any] = [run_id, status]
    if chunk_count is not None:
        args.append(chunk_count)
        sets.append(f"chunk_count = ${len(args)}")
    if cluster_counts is not None:
        keys = (
            "cluster_count_l1", "cluster_count_l2", "cluster_count_l3",
            "cluster_count_l4", "cluster_count_l5",
        )
        for key, count in zip(keys, cluster_counts):
            args.append(count)
            sets.append(f"{key} = ${len(args)}")
    if notes is not None:
        args.append(notes)
        sets.append(f"notes = ${len(args)}")
    if status in ("succeeded", "failed", "superseded"):
        sets.append("finished_at = now()")
    await db.execute(
        f"UPDATE projection_runs SET {', '.join(sets)} WHERE id = $1::uuid",
        *args,
    )


# ─── Stage: fit ────────────────────────────────────────────────────


async def _fetch_sample_embeddings(
    db: Database, sample_size: int,
) -> tuple[list[str], np.ndarray]:
    """Fetch a uniform-random sample of chunks with non-null embeddings.

    Returns (ids, vectors[N, 1024]). For sample_size = 500k this loads
    ~2 GB of float32.

    Strategy: size TABLESAMPLE BERNOULLI's pct to produce ~2.5x the
    target so LIMIT is reliably reachable, then take the first N. No
    ORDER BY random() — TABLESAMPLE is already random and the sort
    over 1M+ rows would blow the 60s asyncpg pool timeout. We bump the
    timeout for this query anyway because pgvector text encoding of
    1024-dim vectors is non-trivial work.
    """
    total = await _fetch_total_chunk_count(db)
    if total == 0:
        return [], np.zeros((0, 1024), dtype=np.float32)
    pct = min(80.0, max(0.5, (sample_size * 250.0) / total))
    log.info(
        "fit: fetching ~%d rows via TABLESAMPLE BERNOULLI(%.2f) on %d total chunks...",
        sample_size, pct, total,
    )
    rows = await db.fetch(
        f"""
        SELECT id::text AS id, embedding::text AS emb
        FROM speech_chunks TABLESAMPLE BERNOULLI({pct})
        WHERE embedding IS NOT NULL
        LIMIT $1
        """,
        sample_size,
        timeout=600.0,
    )
    ids = [r["id"] for r in rows]
    vecs = np.stack([_parse_vector(r["emb"]) for r in rows]) if rows else np.zeros((0, 1024), dtype=np.float32)
    log.info("fit: sample loaded %d rows, shape=%s", len(rows), vecs.shape)
    return ids, vecs


async def _fetch_total_chunk_count(db: Database) -> int:
    return int(await db.fetchval(
        "SELECT count(*) FROM speech_chunks WHERE embedding IS NOT NULL",
        timeout=600.0,
    ))


def _fit_umap(vectors: np.ndarray, n_components: int) -> Any:
    """Sync UMAP fit. Called via asyncio.to_thread to avoid blocking."""
    import umap  # heavy import; defer
    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        metric="cosine",
        random_state=UMAP_RANDOM_STATE,
        verbose=True,
    )
    reducer.fit(vectors)
    return reducer


def _transform_umap(reducer: Any, vectors: np.ndarray) -> np.ndarray:
    return reducer.transform(vectors).astype(np.float32, copy=False)


async def _transform_all_chunks(
    db: Database, run_id: str,
    reducer_3d: Any, reducer_2d: Any,
    *, batch_size: int = DEFAULT_TRANSFORM_BATCH,
    limit: Optional[int] = None,
) -> int:
    """Transform every chunk's embedding in batches; INSERT projections.

    The batch size trades memory for round-trip count. 50k * 1024 * 4
    bytes = 200 MB per batch on the Python side; the DB write fans out
    to one UNNEST call.
    """
    rows_written = 0

    # Page by primary key to keep memory bounded. ON CONFLICT DO UPDATE
    # makes this safe to re-run from scratch on the same run_id; if a
    # run was interrupted, simply re-invoke and rows are upserted.
    # Keyset pagination by primary key. We deliberately avoid
    # `WHERE embedding IS NOT NULL` here: that filter combined with
    # ORDER BY id pushed the planner toward a Bitmap Heap Scan + sort
    # that needed ~55 GB of temp space (3.4M rows * ~16KB each, the
    # pgvector text encoding) and crashed on disk-full. With the
    # filter removed the planner uses a pkey forward-range scan that
    # streams rows incrementally — no sort spill. NULL embeddings
    # (rare; new chunks awaiting the embedder) are filtered in
    # Python and silently skipped; they'll be picked up on the next
    # projection run after embed-speech-chunks catches up.
    SENTINEL_LOW = "00000000-0000-0000-0000-000000000000"
    last_id: str = SENTINEL_LOW
    while True:
        # Subtle gotcha: aliasing `id::text AS id` shadows the column
        # name and forces ORDER BY id to sort on the text projection
        # rather than the indexed UUID column. Keep the alias distinct
        # ('chunk_id') so ORDER BY id resolves to the pkey-indexed
        # column and Postgres uses an in-order forward index scan.
        rows = await db.fetch(
            """
            SELECT id AS chunk_id, embedding::text AS emb
            FROM speech_chunks
            WHERE id > $2::uuid
            ORDER BY id
            LIMIT $1
            """,
            batch_size, last_id,
            timeout=600.0,
        )
        if not rows:
            break
        # Skip rows with NULL embedding; track last_id off the raw row
        # ordering so the next batch boundary is correct.
        usable = [r for r in rows if r["emb"] is not None]
        last_id = str(rows[-1]["chunk_id"])
        if not usable:
            continue
        ids = [str(r["chunk_id"]) for r in usable]
        vecs = np.stack([_parse_vector(r["emb"]) for r in usable])

        coords3 = await asyncio.to_thread(_transform_umap, reducer_3d, vecs)
        coords2 = await asyncio.to_thread(_transform_umap, reducer_2d, vecs)

        await db.execute(
            """
            INSERT INTO speech_chunk_projections
                (chunk_id, run_id, x, y, z, x2, y2)
            SELECT v.id, $1::uuid, v.x, v.y, v.z, v.x2, v.y2
            FROM UNNEST($2::uuid[], $3::real[], $4::real[], $5::real[],
                        $6::real[], $7::real[]) AS v(id, x, y, z, x2, y2)
            ON CONFLICT (chunk_id) DO UPDATE
                SET run_id = EXCLUDED.run_id,
                    x = EXCLUDED.x, y = EXCLUDED.y, z = EXCLUDED.z,
                    x2 = EXCLUDED.x2, y2 = EXCLUDED.y2,
                    cluster_id_l1 = NULL, cluster_id_l2 = NULL,
                    cluster_id_l3 = NULL, cluster_id_l4 = NULL,
                    cluster_id_l5 = NULL,
                    projected_at = now()
            """,
            run_id,
            ids,
            coords3[:, 0].tolist(),
            coords3[:, 1].tolist(),
            coords3[:, 2].tolist(),
            coords2[:, 0].tolist(),
            coords2[:, 1].tolist(),
            timeout=600.0,
        )
        rows_written += len(usable)
        log.info("transform: wrote %d projections (total %d)", len(usable), rows_written)
        if limit is not None and rows_written >= limit:
            log.info("transform: --limit %d reached, stopping", limit)
            break
    return rows_written


async def fit(
    db: Database, *, run_id: Optional[str] = None,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    transform_batch: int = DEFAULT_TRANSFORM_BATCH,
    limit: Optional[int] = None,
) -> tuple[str, FitStats]:
    """Stage 1: fit UMAP and write coords. Returns (run_id, stats)."""
    import time

    stats = FitStats()
    if run_id is None:
        run_id = await create_run(db, {
            "umap": {
                "n_neighbors": UMAP_N_NEIGHBORS, "min_dist": UMAP_MIN_DIST,
                "random_state": UMAP_RANDOM_STATE,
            },
            "sample_size": sample_size,
            "embed_model_tag": os.environ.get("EMBED_MODEL_TAG", "qwen3-embedding-0.6b"),
        })
        log.info("fit: created run %s", run_id)

    stats.chunks_seen = await _fetch_total_chunk_count(db)
    log.info("fit: %d total chunks with embeddings", stats.chunks_seen)
    if stats.chunks_seen == 0:
        log.warning("fit: nothing to project — embedding column is empty")
        return run_id, stats

    sample_n = min(sample_size, stats.chunks_seen)
    _, sample_vecs = await _fetch_sample_embeddings(db, sample_n)
    stats.sample_size = sample_vecs.shape[0]

    t0 = time.perf_counter()
    reducer_3d = await asyncio.to_thread(_fit_umap, sample_vecs, 3)
    stats.fit_seconds_3d = time.perf_counter() - t0
    log.info("fit: UMAP-3D fit done in %.1fs", stats.fit_seconds_3d)

    t0 = time.perf_counter()
    reducer_2d = await asyncio.to_thread(_fit_umap, sample_vecs, 2)
    stats.fit_seconds_2d = time.perf_counter() - t0
    log.info("fit: UMAP-2D fit done in %.1fs", stats.fit_seconds_2d)

    # Free the sample memory before transforming the whole corpus.
    del sample_vecs

    t0 = time.perf_counter()
    stats.rows_written = await _transform_all_chunks(
        db, run_id, reducer_3d, reducer_2d,
        batch_size=transform_batch, limit=limit,
    )
    stats.transform_seconds = time.perf_counter() - t0

    return run_id, stats


# ─── Stage: cluster ────────────────────────────────────────────────


def _hdbscan_cluster(
    coords: np.ndarray,
    min_cluster_size: int,
    sample_size: int = HDBSCAN_SAMPLE_SIZE,
) -> np.ndarray:
    """HDBSCAN on a uniform sample, then nearest-centroid assignment for
    the remainder. See HDBSCAN_SAMPLE_SIZE for why."""
    import hdbscan

    n = coords.shape[0]
    # min_samples is the k for k-NN core-distance computation. Defaults
    # to min_cluster_size when unset — at mcs=2000 that means each point
    # stores 2000 neighbours, yielding ~8 GB k-NN buffers per joblib
    # worker × 4 workers = 32 GB. With min_samples=5 the buffer is ~20 MB.
    # The HDBSCAN docs recommend low min_samples for large datasets;
    # cluster-granularity is governed by min_cluster_size, not min_samples.
    # core_dist_n_jobs=2 keeps a touch of parallelism without ballooning
    # the per-worker memory beyond the cgroup cap.
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=5,
        metric="euclidean",
        core_dist_n_jobs=2,
        approx_min_span_tree=True,
    )

    if n <= sample_size:
        return clusterer.fit_predict(coords).astype(np.int32)

    rng = np.random.default_rng(HDBSCAN_SAMPLE_SEED)
    sample_idx = rng.choice(n, size=sample_size, replace=False)
    sample = coords[sample_idx]
    log.info(
        "cluster: fitting HDBSCAN on %d-point sample (full=%d, mcs=%d)",
        sample_size, n, min_cluster_size,
    )
    sample_labels = clusterer.fit_predict(sample)

    unique = sorted({int(x) for x in sample_labels} - {-1})
    if not unique:
        # HDBSCAN found no density-stable clusters in the sample. Fall
        # through with all-noise rather than crashing the pipeline.
        log.warning("cluster: sample produced 0 clusters at mcs=%d", min_cluster_size)
        return np.full(n, -1, dtype=np.int32)

    centroids = np.zeros((len(unique), coords.shape[1]), dtype=np.float32)
    for i, cl in enumerate(unique):
        mask = sample_labels == cl
        centroids[i] = sample[mask].mean(axis=0)

    # Lazy import: sklearn pulls scipy into RSS even for trivial uses.
    from sklearn.neighbors import KDTree
    tree = KDTree(centroids)
    _, nn_idx = tree.query(coords, k=1)
    label_lookup = np.asarray(unique, dtype=np.int32)
    log.info(
        "cluster: assigned %d points to %d sample-derived centroids",
        n, len(unique),
    )
    return label_lookup[nn_idx.ravel()]


async def cluster(
    db: Database, *, run_id: str,
    min_sizes: Sequence[int] = HDBSCAN_MIN_SIZES,
) -> ClusterStats:
    """Stage 2: HDBSCAN at five levels on the 3D coords. Writes clusters
    and updates speech_chunk_projections.cluster_id_lN. Each level fits
    HDBSCAN on a uniform sample (HDBSCAN_SAMPLE_SIZE) and assigns the
    remaining points by nearest centroid — running over the full corpus
    OOMs the box."""
    import time

    stats = ClusterStats()

    # Idempotent re-run: clear any prior cluster rows + FK references
    # for this run_id before re-clustering. Done as two passes because
    # a single DELETE relies on the FK's ON DELETE SET NULL cascade
    # rewriting 5 cluster_id_lN columns across all projection rows of
    # the run (4.9M × 5 ≈ 25M cell writes), which routinely overruns
    # asyncpg's default timeout. Pre-NULLing the FK columns lets the
    # subsequent DELETE run with no cascade work to do.
    log.info("cluster: clearing prior cluster_id_lN FK references...")
    await db.execute(
        """
        UPDATE speech_chunk_projections
           SET cluster_id_l1 = NULL, cluster_id_l2 = NULL,
               cluster_id_l3 = NULL, cluster_id_l4 = NULL,
               cluster_id_l5 = NULL
         WHERE run_id = $1::uuid
        """,
        run_id,
        timeout=1800.0,
    )
    deleted = await db.execute(
        "DELETE FROM speech_clusters WHERE run_id = $1::uuid",
        run_id,
        timeout=600.0,
    )
    log.info("cluster: cleared prior cluster rows for run %s: %s", run_id, deleted)

    log.info("cluster: loading projections for run %s...", run_id)
    rows = await db.fetch(
        """
        SELECT chunk_id::text AS chunk_id, x, y, z, x2, y2
        FROM speech_chunk_projections
        WHERE run_id = $1::uuid
        ORDER BY chunk_id
        """,
        run_id,
        timeout=600.0,
    )
    if not rows:
        raise RuntimeError(f"cluster: no projection rows for run {run_id}")

    chunk_ids = [r["chunk_id"] for r in rows]
    coords_3d = np.array(
        [[r["x"], r["y"], r["z"]] for r in rows], dtype=np.float32,
    )
    coords_2d = np.array(
        [[r["x2"], r["y2"]] for r in rows], dtype=np.float32,
    )
    log.info("cluster: %d points loaded; running HDBSCAN at %d levels", len(chunk_ids), len(min_sizes))

    # Level → array of cluster labels (one per chunk; -1 for noise).
    level_labels: dict[int, np.ndarray] = {}
    t0 = time.perf_counter()
    for level, mcs in enumerate(min_sizes, start=1):
        log.info("cluster: level %d (min_cluster_size=%d)...", level, mcs)
        labels = await asyncio.to_thread(_hdbscan_cluster, coords_3d, mcs)
        level_labels[level] = labels
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise = int((labels == -1).sum())
        stats.level_counts[level] = n_clusters
        stats.noise_per_level[level] = n_noise
        log.info("cluster: level %d → %d clusters, %d noise", level, n_clusters, n_noise)
    stats.cluster_seconds = time.perf_counter() - t0

    # Build hierarchy: each L2 cluster's parent is the L1 cluster
    # containing the plurality of its members. Same L2→L3, L3→L4, L4→L5.
    log.info("cluster: building parent links via majority vote...")
    parent_l2_to_l1 = _majority_vote_parent(level_labels[2], level_labels[1])
    parent_l3_to_l2 = _majority_vote_parent(level_labels[3], level_labels[2])
    parent_l4_to_l3 = _majority_vote_parent(level_labels[4], level_labels[3]) if 4 in level_labels else {}
    parent_l5_to_l4 = _majority_vote_parent(level_labels[5], level_labels[4]) if 5 in level_labels else {}

    # Compute centroids per (level, cluster_label).
    cluster_records: list[dict[str, Any]] = []
    for level, labels in level_labels.items():
        unique = sorted(set(int(x) for x in labels) - {-1})
        for cl in unique:
            mask = labels == cl
            cluster_records.append({
                "level": level,
                "label_orig": cl,  # HDBSCAN's int label (0..N-1)
                "member_count": int(mask.sum()),
                "centroid_x": float(coords_3d[mask, 0].mean()),
                "centroid_y": float(coords_3d[mask, 1].mean()),
                "centroid_z": float(coords_3d[mask, 2].mean()),
                "centroid_x2": float(coords_2d[mask, 0].mean()),
                "centroid_y2": float(coords_2d[mask, 1].mean()),
            })

    # Insert clusters in level order so parent_id can be resolved.
    # (id_orig, level) -> bigserial id from the DB.
    orig_to_db: dict[tuple[int, int], int] = {}
    log.info("cluster: writing %d cluster rows...", len(cluster_records))
    for record in cluster_records:
        level = record["level"]
        cl = record["label_orig"]
        parent_db_id: Optional[int] = None
        if level == 2:
            parent_orig = parent_l2_to_l1.get(cl)
            if parent_orig is not None and parent_orig != -1:
                parent_db_id = orig_to_db.get((1, parent_orig))
        elif level == 3:
            parent_orig = parent_l3_to_l2.get(cl)
            if parent_orig is not None and parent_orig != -1:
                parent_db_id = orig_to_db.get((2, parent_orig))
        elif level == 4:
            parent_orig = parent_l4_to_l3.get(cl)
            if parent_orig is not None and parent_orig != -1:
                parent_db_id = orig_to_db.get((3, parent_orig))
        elif level == 5:
            parent_orig = parent_l5_to_l4.get(cl)
            if parent_orig is not None and parent_orig != -1:
                parent_db_id = orig_to_db.get((4, parent_orig))

        # Placeholder label / top_terms — filled in the label stage.
        new_id = await db.fetchval(
            """
            INSERT INTO speech_clusters
                (run_id, level, parent_id, label, top_terms, member_count,
                 centroid_x, centroid_y, centroid_z,
                 centroid_x2, centroid_y2, top_chunk_ids)
            VALUES ($1::uuid, $2, $3, $4, $5::jsonb, $6,
                    $7, $8, $9, $10, $11, $12::uuid[])
            RETURNING id
            """,
            run_id, level, parent_db_id,
            f"(unlabelled cluster {level}.{cl})",
            json.dumps([]),
            record["member_count"],
            record["centroid_x"], record["centroid_y"], record["centroid_z"],
            record["centroid_x2"], record["centroid_y2"],
            [],  # top_chunk_ids filled in label stage
        )
        orig_to_db[(level, cl)] = int(new_id)

    # Update speech_chunk_projections with cluster_id_lN. Build per-chunk
    # arrays of (l1..l5) DB ids and write via UNNEST. Levels with no
    # corresponding label array (sparse run) write None → NULL.
    log.info("cluster: stamping cluster_id_lN onto projection rows...")
    BATCH = 50_000
    for start in range(0, len(chunk_ids), BATCH):
        end = min(start + BATCH, len(chunk_ids))
        ids_b = chunk_ids[start:end]
        l1_b = [
            orig_to_db.get((1, int(level_labels[1][i])))
            for i in range(start, end)
        ]
        l2_b = [
            orig_to_db.get((2, int(level_labels[2][i])))
            for i in range(start, end)
        ]
        l3_b = [
            orig_to_db.get((3, int(level_labels[3][i])))
            for i in range(start, end)
        ]
        l4_b = [
            orig_to_db.get((4, int(level_labels[4][i])))
            for i in range(start, end)
        ] if 4 in level_labels else [None] * (end - start)
        l5_b = [
            orig_to_db.get((5, int(level_labels[5][i])))
            for i in range(start, end)
        ] if 5 in level_labels else [None] * (end - start)
        await db.execute(
            """
            UPDATE speech_chunk_projections AS p
               SET cluster_id_l1 = v.l1,
                   cluster_id_l2 = v.l2,
                   cluster_id_l3 = v.l3,
                   cluster_id_l4 = v.l4,
                   cluster_id_l5 = v.l5
              FROM UNNEST($1::uuid[], $2::bigint[], $3::bigint[], $4::bigint[],
                          $5::bigint[], $6::bigint[])
                   AS v(id, l1, l2, l3, l4, l5)
             WHERE p.chunk_id = v.id AND p.run_id = $7::uuid
            """,
            ids_b, l1_b, l2_b, l3_b, l4_b, l5_b, run_id,
            timeout=600.0,
        )
        log.info("cluster: stamped projections %d–%d", start, end)

    return stats


def _majority_vote_parent(
    child_labels: np.ndarray, parent_labels: np.ndarray,
) -> dict[int, int]:
    """For each unique child label != -1, return the parent label that
    occurs most often among its members. Skips child=-1."""
    out: dict[int, int] = {}
    for child in sorted(set(int(x) for x in child_labels) - {-1}):
        mask = child_labels == child
        parents = parent_labels[mask]
        # Majority vote ignoring noise (-1) when possible.
        non_noise = parents[parents != -1]
        if len(non_noise) > 0:
            values, counts = np.unique(non_noise, return_counts=True)
            out[child] = int(values[counts.argmax()])
        else:
            out[child] = -1
    return out


# ─── Stage: label ──────────────────────────────────────────────────


async def label(db: Database, *, run_id: str) -> LabelStats:
    """Stage 3: per-cluster TF-IDF labelling.

    For each cluster: fetch member chunk text (capped at
    LABEL_MAX_DOCS_PER_CLUSTER for huge clusters), compute TF-IDF, take
    the top-N terms by mean weight, persist label + top_terms +
    top_chunk_ids (15 closest to centroid).
    """
    import time
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

    stops = list(ENGLISH_STOP_WORDS | FRENCH_STOPWORDS)
    stats = LabelStats()
    t0 = time.perf_counter()

    clusters = await db.fetch(
        """
        SELECT id, level, member_count, centroid_x, centroid_y, centroid_z, label
        FROM speech_clusters WHERE run_id = $1::uuid
        ORDER BY level, member_count DESC
        """,
        run_id,
    )
    n_total = len(clusters)
    n_already = sum(
        1 for c in clusters
        if c["label"] and not c["label"].startswith("(unlabelled ")
    )
    log.info(
        "label: %d clusters total (%d already labelled, %d to do)",
        n_total, n_already, n_total - n_already,
    )

    for cluster_row in clusters:
        cluster_id = int(cluster_row["id"])
        level = int(cluster_row["level"])
        cap = LABEL_MAX_DOCS_PER_CLUSTER

        # Resume support: skip clusters that already have a real label.
        # If a previous label run died mid-loop (transient DB blip,
        # external SIGKILL, etc.) re-running this stage picks up only
        # the remaining clusters instead of redoing thousands of TF-IDF
        # fits. Placeholder labels of the form "(unlabelled cluster …)"
        # are treated as not-yet-done.
        existing = cluster_row["label"]
        if existing and not existing.startswith("(unlabelled "):
            stats.clusters_labelled += 1
            continue

        chunks = await db.fetch(
            f"""
            SELECT ch.id::text AS id, ch.text,
                   p.x, p.y, p.z
            FROM speech_chunk_projections p
            JOIN speech_chunks ch ON ch.id = p.chunk_id
            WHERE p.run_id = $1::uuid
              AND p.cluster_id_l{level} = $2
            ORDER BY random()
            LIMIT $3
            """,
            run_id, cluster_id, cap,
        )
        if not chunks:
            continue
        stats.chunks_read += len(chunks)

        texts = [c["text"] or "" for c in chunks]
        try:
            vec = TfidfVectorizer(
                stop_words=stops,
                lowercase=True,
                strip_accents="unicode",
                token_pattern=r"(?u)\b[a-zA-ZàâäéèêëïîôöùûüÿçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ]{3,}\b",
                min_df=LABEL_MIN_DF,
                max_df=LABEL_MAX_DF,
                ngram_range=LABEL_NGRAM,
                max_features=LABEL_MAX_FEATURES,
            )
            X = vec.fit_transform(texts)
        except ValueError:
            # min_df/max_df can leave zero terms on tiny clusters.
            await db.execute(
                "UPDATE speech_clusters SET label = $2 WHERE id = $1",
                cluster_id, f"(unlabelled cluster {level}.{cluster_id})",
            )
            continue

        weights = np.asarray(X.mean(axis=0)).ravel()
        terms = vec.get_feature_names_out()
        order = weights.argsort()[::-1]
        top_n = order[:LABEL_TOP_TERMS_KEEP]
        top_terms_list = [
            {"term": terms[i], "weight": float(weights[i])}
            for i in top_n if weights[i] > 0
        ]
        label_str = ", ".join(t["term"] for t in top_terms_list[:LABEL_TOP_N]) \
                    or f"(unlabelled cluster {level}.{cluster_id})"

        # Pick representatives: 15 chunks closest to centroid_3d.
        cx, cy, cz = (
            float(cluster_row["centroid_x"]),
            float(cluster_row["centroid_y"]),
            float(cluster_row["centroid_z"]),
        )
        coords = np.array(
            [[c["x"], c["y"], c["z"]] for c in chunks], dtype=np.float32,
        )
        dists = np.linalg.norm(coords - np.array([cx, cy, cz]), axis=1)
        nearest_idx = dists.argsort()[:LABEL_TOP_CHUNK_IDS]
        top_chunk_ids = [chunks[int(i)]["id"] for i in nearest_idx]

        await db.execute(
            """
            UPDATE speech_clusters
               SET label = $2,
                   top_terms = $3::jsonb,
                   top_chunk_ids = $4::uuid[]
             WHERE id = $1
            """,
            cluster_id, label_str,
            json.dumps(top_terms_list),
            top_chunk_ids,
        )
        stats.clusters_labelled += 1

    stats.seconds = time.perf_counter() - t0
    return stats


# ─── Stage: promote / gc ────────────────────────────────────────────


async def promote(db: Database, *, run_id: str) -> None:
    """Atomically flip is_current to the new run.

    Also marks the run 'succeeded' if it isn't already, and any other
    is_current=true rows 'superseded'.
    """
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE projection_runs
                   SET is_current = false,
                       status = 'superseded',
                       finished_at = COALESCE(finished_at, now())
                 WHERE is_current = true AND id <> $1::uuid
                """,
                run_id,
            )
            await conn.execute(
                """
                UPDATE projection_runs
                   SET is_current = true,
                       status = CASE WHEN status = 'running' THEN 'succeeded' ELSE status END,
                       finished_at = COALESCE(finished_at, now())
                 WHERE id = $1::uuid
                """,
                run_id,
            )


async def gc(db: Database, *, max_age_days: int = 7) -> int:
    """Drop superseded/failed runs older than max_age_days. Cascades kill
    cluster + projection rows for those runs. Never drops the current."""
    deleted = await db.fetchval(
        """
        WITH del AS (
            DELETE FROM projection_runs
             WHERE is_current = false
               AND status IN ('superseded','failed')
               AND COALESCE(finished_at, started_at) < now() - ($1 || ' days')::interval
            RETURNING id
        )
        SELECT count(*) FROM del
        """,
        str(max_age_days),
    )
    return int(deleted or 0)
