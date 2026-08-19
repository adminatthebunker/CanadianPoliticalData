Draft `BoundarySpec` files, one per jurisdiction, used with
`load-boundaries --spec-file` so a spec can be written and `--compare`d without
editing the shared `SPECS` registry in `boundary_loader.py`.

Each file defines exactly `SPEC = BoundarySpec(...)` and is executed with
`boundary_loader`'s namespace already populated, so `BoundarySpec`, `date` and
`SPECS` are all in scope without imports.

Run from the repo root:

    docker compose run --rm scanner load-boundaries \
      --spec-file /app/src/legislative/_draft_specs/<jurisdiction>.py --compare

Once a spec is reviewed it moves into `SPECS` and its draft file is deleted.
