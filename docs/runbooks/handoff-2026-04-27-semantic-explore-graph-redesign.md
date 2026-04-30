# Handoff — 2026-04-27 → 2026-04-28 (Semantic explorer — render polish + graph view shipped, next: production projection + commit + proper edges)

**Session arc:** picked up from the smoke-projection state (45k chunks, 36 L3 clusters, browser view = "two flat balls in a void"). Two passes happened:

1. **Render polish + UX fixes** (2026-04-28). FOV-aware camera framing, R3F canvas-fill bug, Stars + radial-gradient background, physical material + clearcoat, HSL golden-ratio palette, hover-focus mode, label HTML overlay, cluster centroid spread (`CLUSTER_SPREAD = 2.5`), `SemanticMapHints` overlay with reset-view, scroll-zoom snap-back fix, mode-toggle URL bug fix.
2. **Graph view (client-side proxy)**. K-NN edges by UMAP centroid distance — drei `<Line>` in 3D, SVG `<line>` in 2D, hover-aware highlighting. This is *not* the full migration-0040 cosine-similarity edges from the original plan; it's a 30-min client-side approximation that ships today. The proper version is still on the table.

**Committed:** **still nothing.** Everything below remains uncommitted on local `main`. Suggested commit split is in § "Files to commit."

**Current promoted run:** `7d2707af-e165-4ac1-91eb-c80dc690eb3e` — 45k chunks, 36 L3 clusters. Live at `http://localhost:8088/semantic-map` (or `https://canadianpoliticaldata.ca/semantic-map`).

---

## TL;DR — first three things next session

1. **Run the full-corpus production projection.** Same commands as the prior handoff; takes 60–90 min CPU. After this, the L1/L2/L3 hierarchy gets real shape (~30/200/1500 clusters instead of today's 2/2/36) and the polished UI lights up properly.
   ```bash
   docker compose run --rm scanner project-embeddings --stage=fit --sample-size=500000
   docker compose run --rm scanner project-embeddings --stage=cluster --run-id=<from fit>
   docker compose run --rm scanner project-embeddings --stage=label  --run-id=<...>
   docker compose run --rm scanner project-embeddings --stage=promote --run-id=<...>
   ```
   No GPU contention with TEI — pipeline only reads `speech_chunks.embedding`. Drop `--rm` if you want post-mortem logs.

2. **Commit the work.** All 1700+ lines of feature surface are still uncommitted. Suggested split below; do this before further changes so the history is clean and you can diff future iterations against a real baseline.

3. **Decide whether to ship migration 0040 (real cluster edges).** The current K-NN-by-UMAP-distance approach in the renderer is good enough for the smoke run but degrades at scale: at 1500 L3 clusters, computing all-pairs distance client-side per frame becomes a problem (~2.2M comparisons), AND UMAP distances are a lossy proxy for cosine in original embedding space. Migration 0040 (centroid_embedding column + speech_cluster_edges table) is the durable fix. Sketch is at the bottom of this doc.

---

## What got fixed this session

### Render polish (3D + 2D)

- **FOV-aware camera framing.** `CameraFitter` in `ClusterCloud3D.tsx:240+`. Per-axis half-extents (`distY = halfY/tan(θ/2)`, `distX = halfX/(aspect·tan(θ/2))`) instead of bounding-sphere radius. Without this, sparse 2-cluster scenes had centroids floating at the top of the canvas because the magic-number `span × 1.6` over-distanced.
- **R3F canvas filling its container.** This was the biggest find of the day. `<Canvas>` wraps in a div with inline `height: 100%`. CSS percentage heights only resolve against an explicit `height` on the parent — `min-height` is *not* enough. The flex container with `min-height: 78vh` resulted in a 150-px-tall WebGL canvas. Fix: `.semantic-map__stage > .semantic-map__canvas { position: absolute !important; inset: 0; }` against the stage's `position: relative`. See § Pitfalls #5 below.
- **Materials + lighting.** `meshPhysicalMaterial` with `roughness=0.35`, `clearcoat=0.6`, color-tinted emissive at 0.18 (idle) / 0.6 (hovered). Three-point lighting: warm key (`#fef3c7`), cool fill (`#7dd3fc`), white point rim. drei `<Stars radius={120} depth={60} count={2000}>` for depth.
- **Background = radial gradient on the stage div.** `<Canvas alpha={true}>` makes WebGL transparent; the stage shows a CSS radial-gradient through it. `box-shadow: inset 0 0 60px rgba(0,0,0,0.45)` adds a vignette.
- **HSL golden-ratio palette.** `colorFor(id)` uses `hue = (id × φ) mod 1 × 360°` with sat 70–90% / lit 58–70%. Sequential cluster IDs get maximally distinct hues; this is the load-bearing change for L3 distinguishability when 35+ clusters pack the same volume.
- **Hover-focus mode.** Hovered cluster scales `1.12×`, gets bright emissive + white halo + shows label. Non-hovered fade to 22% opacity, halos suppressed (in dense scenes only the hovered cluster gets a halo). Wireframe outline ring at `r × 1.001` with `meshBasicMaterial color="#0f172a" opacity=0.18` gives idle clusters edge definition without the gridded look on hover.
- **Cluster spread.** `CLUSTER_SPREAD = 2.5` constant in both renderers, applied via `spread()` helper to centroids only (NOT radii). UMAP packs semantically-similar topics tight; this exaggerates the gaps for legibility while preserving relative distances. Single source of truth — every centroid read in each file goes through `spread()`. Camera fitter accounts for it in bbox calc, so the camera pulls back proportionally; the perceived gain on screen is ~60% (the math is in CLUSTER_SPREAD's comment block).
- **Per-density label cap.** `≤12 → all, ≤25 → 14, ≤50 → 12, else 10`, sorted by `member_count`. Same caps in 2D and 3D.

### Labels rendering as `<Html>`, not `<Text>`

drei `<Text>` (troika-three-text under the hood) ignored `material-depthTest={false}` on the SDF material — labels got occluded by intervening spheres ("président, loi" rendered as "lent, loi" because the orange sphere's depth ate the leading characters). Switched to drei `<Html>` overlays positioned at `[0, r × 1.18, 0]` with `zIndexRange={[100, 0]}`. CSS in `.semantic-map__cluster-label*`. Bulletproof — DOM elements positioned via 3D projection, depth never applies.

### Scroll-to-zoom snap-back (the bug)

`CameraFitter`'s `useFrame` was lerping the camera every frame toward `targetRef.current`. OrbitControls wrote on user input, CameraFitter wrote on RAF — last writer wins, fitter ran 60×/sec, user zoom got instantly stolen. Fix: lerp is now **event-driven**:

- `transitioningRef` flag — only true while a snap is in progress.
- Set true in the data-change `useEffect` (drilldown, breadcrumb, filter).
- `useFrame` returns immediately if `!transitioningRef.current`.
- Listen for `controls.addEventListener("start", onStart)` — OrbitControls fires this on user input — and set `transitioningRef.current = false`.
- Also clear when camera/target are within 0.5% of fit distance (so the lerp doesn't run forever).

Belt-and-suspenders CSS: `touch-action: none` on the canvas + `overscroll-behavior: contain` on the stage so wheel/touch can't bleed through to page scroll.

### Reset view button

`ClusterCloud3D` accepts a `resetSignal: number` prop. Parent (`SemanticMapPage`) holds `useState(0)`; the hint button calls `setResetSignal(n => n + 1)`. A second `useEffect` in `CameraFitter` watches `resetSignal` and snaps the camera position + `controls.target` back to the canonical view direction `(0, 0.25, 1).normalize() × dist`. The signal value itself is meaningless — only the change matters.

### Mode-toggle URL bug fix

`writeUrl` in `SemanticMapPage.tsx:65` was skipping `mode=` when `mode === "2d"` (the assumed default). On *desktop* the default is 3d (`isTouch ? "2d" : "3d"`), so clicking the 2D toggle produced a URL with no `mode` param, `readMode` fell back to 3d, and the toggle silently failed. Fix: write mode unconditionally. Three extra characters; toggle is deterministic on both touch and desktop.

### Spider-web edges (client-side K-NN)

`computeClusterEdges(clusters, k)` in `ClusterCloud3D.tsx:50+` and `computeClusterEdges2D` in `ClusterCloud2D.tsx`. K scales with density: ≤12 → 4, ≤30 → 3, else 2. For each cluster, top-K nearest by UMAP centroid distance; emit each edge once (`src.id < dst.id` dedup). Similarity = `max(0.3, 1 - d / (maxD × 1.4))` — closest neighbour ≈ 1.0, K-th ≈ 0.3.

Rendered via drei `<Line>` (3D) and SVG `<line>` (2D). Edges incident to the hovered cluster pop bright white at 85% opacity; non-incident edges fade to 25% — gives "what does this cluster connect to" at a glance.

**Caveats:**
- O(N²) per render at L1/L2 is fine, but at the production L3 (~1500 clusters) this is 2.2M comparisons in `useMemo`. Probably still acceptable since `useMemo` only fires on `clusters` change, not every frame, but worth profiling.
- UMAP distance ≠ cosine similarity. UMAP preserves *local* structure well but discards global structure. Two clusters that look close in UMAP-3D may not be the cosine-nearest in 1024-d. For the visualization this is usually fine; for "show me what this cluster is most semantically related to," the proper edges from migration 0040 will be more accurate.

### Navigation hints overlay

`SemanticMapHints.tsx`. Floating panel anchored to bottom-right of the stage. Auto-collapses to a small `?` button after 8 seconds OR when `level` changes (since available actions change as the user drills). Click to re-expand. Content adapts:

- **3D**: drag to orbit, scroll to zoom, right-drag to pan, hover to focus, click to drill in.
- **2D**: hover + click only.
- **Drill copy**: "Drill into cluster" at L1/L2, "View speeches" at L3 (clicking opens the drawer instead of drilling).

The "Reset view" button (3D only) calls the parent's `setResetSignal(n => n + 1)` to fire the camera snap-back described above.

Why level-keyed timeout, not mount-keyed: the first appearance teaches; the level-change reappearance reminds. Free progressive disclosure.

---

## What's still on the table

### 1. Migration 0040 — real cluster-to-cluster edges

The original plan from the prior handoff. The K-NN-by-UMAP-distance approach we shipped is a proxy; for accuracy and scalability, we still want the proper version:

```sql
-- db/migrations/0040_speech_cluster_edges.sql
alter table speech_clusters
  add column centroid_embedding vector(1024);

create table speech_cluster_edges (
    id              bigserial primary key,
    run_id          uuid not null references projection_runs(id) on delete cascade,
    src_cluster_id  bigint not null references speech_clusters(id) on delete cascade,
    dst_cluster_id  bigint not null references speech_clusters(id) on delete cascade,
    similarity      real   not null,    -- cosine in 1024-d
    rank            smallint not null,  -- 1..K within src
    unique (src_cluster_id, dst_cluster_id),
    check (src_cluster_id <> dst_cluster_id)
);
create index idx_cluster_edges_run on speech_cluster_edges(run_id, src_cluster_id);
```

Pipeline change in `services/scanner/src/legislative/projection_builder.py`: a new `--stage=edges` (or fold into `cluster`) that:
1. Streams `speech_chunks.embedding` for each cluster's members in batches; averages → `centroid_embedding`.
2. Cosine-normalises and writes `centroid_embedding`.
3. Computes top-K=8 cosine within each level (sklearn `NearestNeighbors(metric="cosine")` or matmul if level has < 5k clusters).
4. Bulk-inserts `speech_cluster_edges`.

API: fold `neighbors: [{id, similarity}]` into `/projections/clusters` rows. Frontend: replace the client-side `computeClusterEdges` call with a read from `cluster.neighbors`. The `<EdgesLayer>` component is already structured so this is a one-function swap — preserving K-NN proxy as a fallback when the API hasn't shipped neighbors yet would be a nice touch.

Cost estimate: ~5 min CPU at 3.4M chunks for centroid computation; top-K within ~30/200/1500 clusters is < 1 sec.

### 2. Run the full-corpus production projection

See § TL;DR #1.

### 3. Commit everything

See § "Files to commit."

### 4. Lower-priority polish

From the original handoff that wasn't done this session:

- **Hierarchy colour** (each L1 root assigned a hue, L2/L3 children HSL-shifted from parent). Current golden-ratio palette spreads colors maximally but doesn't show parent-child relationship. Worth doing once production projection ships and the L1 hierarchy is meaningful (currently L1 = 2 clusters which doesn't motivate it).
- **Blob shapes (2D)** via convex hull / alpha-shape over sample points from `/projections/points`. Currently 2D shows circles with radial-gradient fills. Real blob shapes are a v2 polish.
- **Edge fade on zoom** — when the user is zoomed deep into one cluster, fade distant edges so the local neighbourhood reads cleanly. Easy to add via a per-edge distance check against camera position in `EdgesLayer`'s render loop.
- **`--limit` semantics in the scanner pipeline** — currently `--limit=N` stops the transform after the *first batch* whose row count exceeds N. Either rename or trim the final batch.
- **TF-IDF stopword preprocessing warning** — sklearn warns about token mismatches in the bilingual stopword list. Cosmetic; fix is `strip_accents="unicode"` applied to stopwords manually before passing them in.

---

## Pitfalls — read before touching code

Pitfalls #1–#7 are scanner/DB gotchas from the prior handoff (still valid — re-read before running the production projection or adding migration 0040). Pitfalls #8–#12 are new from the polish session.

1. **`id::text AS id` aliasing breaks `ORDER BY id`.** Postgres resolves `ORDER BY id` to the SELECT alias when there's a name collision, sorting the text projection instead of the indexed UUID. Planner switches from a 0.4s pkey forward scan to a 220-second seq-scan-and-sort. **Fix:** always pick a different alias name (e.g. `id AS chunk_id`). See `projection_builder.py` transform loop comment.

2. **Off-by-one in incremental `$N` parameter numbering.** `params.push(v); next() = $${startIdx + params.length}` is **wrong** — push has already incremented `length`, so `next()` returns the next slot, not the slot just filled. PG then sees `$3 = 'federal'` in the params list but the SQL references `$4`, leaving `$3` undefined. Error reads `could not determine data type of parameter $3`. **Fix pattern:** the `add()` helper at `projections.ts:90` pushes and returns the correct slot in one step.

3. **Postgres can't infer parameter types inside CTEs.** `WHERE col = $N` works at top-level (planner infers from `col`'s type), fails inside a CTE. Always cast filter parameters explicitly: `$N::text`, `$N::date`, `$N::int`, `$N::uuid`.

4. **Disk-full from sort spill.** `SELECT ... FROM speech_chunks WHERE embedding IS NOT NULL ORDER BY id` over 3.4M rows with text-encoded embeddings spills ~55 GB to `pgsql_tmp` if the planner picks Bitmap Heap Scan + Sort. **Fix:** drop the `WHERE embedding IS NOT NULL` filter (per CLAUDE.md, every chunk is embedded) and let the planner use the pkey forward index scan. Skip NULLs in Python instead.

5. **asyncpg pool `command_timeout=60` is global.** Slow queries hit it as `TimeoutError` after exactly 60s. **Fix:** pass `timeout=600.0` explicitly to `db.fetch/execute` for known-slow ops. The wrapper in `services/scanner/src/db.py` already accepts the kwarg.

6. **Docker BuildKit content-cache miss.** `docker compose build api` may reuse a stale layer even after source bytes have changed. If the running JS still has the old code post-build, run `docker compose build --no-cache api`. Cost ~30 min of red-herring debugging today.

7. **`docker compose run --rm -d` containers vanish on exit.** With `--rm`, the container auto-removes when it crashes — you lose the ability to read its logs. For pipeline runs you might want to debug, drop `--rm` and clean up manually.

8. **R3F `<Canvas>` wrapper collapses in flex containers with only `min-height`.** The wrapper has inline `height: 100%`. CSS percentage heights only resolve against an explicit `height` on the parent — `min-height` is *not* sufficient, even with `align-items: stretch`. Symptom: WebGL canvas renders at 150 px tall (HTMLCanvasElement default) regardless of stage size. **Fix:** pin the wrapper absolutely against a `position: relative` parent — `.semantic-map__stage > .semantic-map__canvas { position: absolute !important; inset: 0; }`. The same gotcha would hit any drei/r3f canvas inside a flex layout that uses `min-height`.

9. **`material-depthTest={false}` on drei `<Text>` doesn't propagate.** troika-three-text uses an SDF material that ignores the prop. Symptom: text labels get partially occluded by intervening 3D geometry (e.g. "président" rendered as "lent" because a foreground sphere's depth ate the leading characters). **Fix:** for "always-on-top" labels, switch to drei `<Html>`. DOM elements positioned via 3D projection — depth ordering doesn't apply at all. The only cost is loss of true 3D scale, but for billboarded labels we don't care.

10. **CameraFitter that lerps every frame steals user input.** Two systems writing to `camera.position` (OrbitControls on input, fitter on RAF) race; if the fitter doesn't gate its writes, scroll-zoom is undone instantly. **Fix pattern:** event-driven lerp — set a `transitioningRef` true on data change, clear it on (a) reaching target, (b) `controls.addEventListener("start", ...)`. Same pattern applies to any "auto-fit" behaviour layered over user-controllable state.

11. **Skip-default URL serialisation breaks toggles when the default is contextual.** `if (mode !== "2d") p.set("mode", mode)` looks reasonable until you remember the default is `isTouch ? "2d" : "3d"` — desktop users clicking 2D produce a URL with no `mode` param, `readMode` returns the desktop default of 3D, toggle silently no-ops. **Fix:** write the param unconditionally, or pass the contextual default into the writer and skip only when they match. The first option is cheaper.

12. **OrbitControls + page scroll need `touch-action: none` on the canvas itself.** R3F sets it on the wrapper div but not the inner `<canvas>` element. Without it, wheel events over the canvas bleed into page scroll even when OrbitControls is consuming them. **Fix:** `.semantic-map__canvas canvas { touch-action: none; }` + `.semantic-map__stage { overscroll-behavior: contain; }`.

---

## Files to commit

**Suggested commit split** (after running `git status` to confirm — the list below is what the explorer feature touches; there's other unrelated work in the tree):

### Commit 1 — Migration + scanner pipeline
- `db/migrations/0039_speech_chunk_projections.sql`
- `services/scanner/src/legislative/projection_builder.py`
- `services/scanner/src/__main__.py` (project-embeddings Click command + `logging.basicConfig`)
- `services/scanner/requirements.txt` (numpy, sklearn, umap-learn, hdbscan)
- `services/scanner/Dockerfile` (build-essential — can be reverted once you confirm wheels were used)

### Commit 2 — API
- `services/api/src/routes/projections.ts`
- `services/api/src/index.ts` (registered routes)

### Commit 3 — Frontend feature shell
- `services/frontend/src/pages/SemanticMapPage.tsx`
- `services/frontend/src/components/semantic-map/ClusterCloud2D.tsx`
- `services/frontend/src/components/semantic-map/ClusterCloud3D.tsx`
- `services/frontend/src/components/semantic-map/ClusterDrawer.tsx`
- `services/frontend/src/components/semantic-map/ModeToggle.tsx`
- `services/frontend/src/components/semantic-map/SemanticMapFilters.tsx`
- `services/frontend/src/components/semantic-map/SemanticMapHints.tsx`
- `services/frontend/src/hooks/useSemanticMap.ts`
- `services/frontend/src/styles/semantic-map.css`
- `services/frontend/src/main.tsx` (routes)
- `services/frontend/src/components/Layout.tsx`, `MobileBottomNav.tsx` (nav links)
- `services/frontend/package.json`, `package-lock.json` (three, r3f, drei)

### Commit 4 — Docs
- `CLAUDE.md` (Semantic mind-map / Explore section)
- `docs/plans/semantic-layer.md` (Phase 7)
- `mkdocs/docs/explore/index.md`
- `mkdocs/mkdocs.yml`
- This handoff doc itself.

### Commit 5+ — When migration 0040 lands
Treat the proper edges as a follow-up commit set: migration + pipeline stage + API additions + frontend swap from K-NN proxy to API-backed edges.

---

## How to verify in the browser after reboot

1. `docker compose up -d db api frontend tei` (TEI optional unless you're re-embedding).
2. Open `http://localhost:8088/semantic-map` (or the Pangolin URL).
3. Confirm the smoke run is still promoted — if not, re-run `--stage=promote --run-id=7d2707af-e165-4ac1-91eb-c80dc690eb3e`.
4. The L1 view should show two well-separated spheres ("member, government, minister" / "une, président, loi") with labels above and a faint web edge connecting them.
5. Drilldown into "member, government, minister" → L2 → L3 (35 clusters). At L3, ~12 labels should be visible. Hover any cluster — it should pop white, neighbours fade, edges incident to it should highlight.
6. Scroll wheel should zoom and *stick* (no snap-back). Right-drag pans. Reset View button in the bottom-right hints panel should snap back to fit.
7. Toggle 2D and confirm both modes work; URL should include `?mode=2d`.

If any of these fail, see the relevant § Pitfall above.

---

## Plan reference

- Original feature plan: `~/.claude/plans/like-selecting-a-phrase-snappy-owl.md`.
- CLAUDE.md "Semantic mind-map / Explore" section is the authoritative architecture reference.
- Prior handoff (this file's predecessor history) for the original graph-redesign brief and the four pitfalls #1–#4.
