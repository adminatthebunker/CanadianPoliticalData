# Scanner tests

Pytest suites for pure functions in `services/scanner/src/`. No DB access at
test time — everything runs off checked-in fixtures.

## Running

`tests/` is **not** mounted by the compose `scanner` service (only `src/`, `db/`,
`scripts/`, and `data/` are), and **pytest is not in `services/scanner/requirements.txt`**,
so the run command bind-mounts the tests and installs pytest into the throwaway
container:

```bash
docker compose run --rm -T \
  -v "$(pwd)/services/scanner/tests:/app/tests" \
  --entrypoint sh scanner \
  -c "pip install -q pytest && python -m pytest /app/tests -q"
```

Two things would simplify this and are worth doing when someone is next editing
the scanner image (deliberately not done here — this task was scoped to `tests/`):

- add `pytest` to `services/scanner/requirements.txt`;
- add `./services/scanner/tests:/app/tests:ro` to the `scanner` service volumes
  in `docker-compose.yml`.

With both in place the command collapses to
`docker compose run --rm -T scanner python -m pytest tests/ -q`.

## `test_caption_pipeline.py` — Edmonton caption golden set

Covers `src/legislative/youtube_captions.py`: `parse_vtt`, `collapse_cc_turns`
(and `_apply_block_alternation`, which it calls), `_cc_recognized_speaker`,
`truecase_caption_text`, and `make_panel_owner_lookup`.

### Fixtures

| File | Source |
| --- | --- |
| `fixtures/exec_committee_2026-08-12.vtt` | `meetings.raw_captions_vtt` for `source_meeting_id = 62e9df40-bc28-4052-9cad-1a9d5d3e0294` (Edmonton Executive Committee, 2026-08-12, YouTube `YAobWoLOnO0`) |
| `fixtures/exec_committee_2026-08-12_panel_timeline.json` | `meetings.raw->'speaker_timeline'` for the same meeting — 51 clerk-panel OCR intervals |

Both are exported read-only from the live DB:

```bash
docker exec sw-db psql -U sw -d sovereignwatch -t -A \
  -c "select raw_captions_vtt from meetings where source_meeting_id='62e9df40-bc28-4052-9cad-1a9d5d3e0294'" \
  > services/scanner/tests/fixtures/exec_committee_2026-08-12.vtt
```

The VTT is ~2.1 MB. It is the golden set precisely because this meeting has been
hand-checked against the diarization cross-check, so treat it as immutable —
re-exporting it is only correct if the upstream VTT itself was refetched.

### What is pinned

The suite pins *current measured behaviour*, not hand-authored ideals. Every
number below was measured against the code as it stands and cross-checked
against the `speeches` rows in the DB for this meeting.

- **Parse**: 4,629 caption lines, 286 `>>` turn markers, no surviving `&gt;` /
  `&amp;` entities, no cue markup.
- **Collapse totals**: 286 turns, attribution counts
  `{None: 139, macro: 72, recognition: 24, alternation: 49, self_intro: 2}`.
  The 139 `None` turns are the 115 that stay bare plus the 24 that a **DB-side
  voice map** later fills in — those 24 are `attribution='voice'` in the DB but
  `None` out of `collapse_cc_turns`, which is why the DB and collapse counts
  differ on that one key and nowhere else.
- **Per-sequence speaker pins**, ~35 turns across all four tiers. Sequence
  numbers are 1-based positions in the collapse output (`index + 1`), which is
  also `speeches.sequence` in the DB.
- **Two named regressions**, each with its own test:
  - `test_chair_prompt_block_phase_is_not_inverted` — the 248–262 block. The
    chair's short un-macro'd prompts are `chair` anchors that reset the
    alternation phase; without that anchor class the phase inverts and credits
    the chair's prompts to the member.
  - `test_relay_guard_keeps_third_party_greeting_unattributed` — seq 6, "And
    good morning from Councillor Wright.", a relayed greeting that must not be
    credited to Wright.
- **Panel guard**: the fixture timeline has 51 intervals, yet collapse output is
  byte-identical with and without it, and no turn ends up `attribution='panel'`.
  That is the "panel-opened blocks need an independent in-block anchor" guard
  doing its job — the test pins the guard, not the absence of a timeline.
- One deliberate oddity is pinned as current behaviour: seq 267 carries a
  mis-fired steno macro naming **Drew Dilkens** (Windsor's mayor) in an Edmonton
  meeting. Collapse trusts macros; cleaning that up belongs to roster
  resolution, not here.

### When to update the pins

Changing an attribution count or a per-sequence speaker is a **behaviour
change**, not a test fix. Before touching the numbers:

1. Re-run the suite and read which pins moved — the tiers are separate tests so
   the diff tells you whether the change was in macro parsing, recognition
   grammar, or block alternation.
2. Confirm the new attributions are actually *better* on the moved turns, by
   eye, against the fixture text.
3. Update the constants at the top of the file
   (`EXPECTED_CAPTION_LINES`, `EXPECTED_TURN_COUNT`,
   `EXPECTED_ATTRIBUTION_COUNTS`) and the affected `*_PINS` lists in the same
   commit as the code change, and say in the commit message which direction the
   accuracy moved.

If a pin moves that you did not intend to touch, that is the harness working.
