"""Golden-set regression tests for the Edmonton broadcast-CC caption pipeline.

Ground truth is the 2026-08-12 Executive Committee meeting (video YAobWoLOnO0,
meeting 62e9df40-bc28-4052-9cad-1a9d5d3e0294), whose VTT is checked in under
fixtures/. No DB access at test time — everything runs off the fixtures.

The attribution counts and per-sequence speaker pins below were measured against
the code as it stands and match the speeches rows currently in the DB for this
meeting. They are behaviour pins, not hand-authored ideals: a diff here means the
attribution machinery moved, and the move needs justifying before the pins are
updated. See README.md.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import pytest

# tests/ sits next to src/ inside the scanner image (/app/tests, /app/src).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.legislative.youtube_captions import (  # noqa: E402
    CaptionLine,
    _cc_recognized_speaker,
    _STATIC_PROPER,
    collapse_cc_turns,
    looks_like_cc_turn_captions,
    make_panel_owner_lookup,
    parse_vtt,
    truecase_caption_text,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VTT_PATH = FIXTURES / "exec_committee_2026-08-12.vtt"
TIMELINE_PATH = FIXTURES / "exec_committee_2026-08-12_panel_timeline.json"

# ── Pinned golden-set numbers (2026-08-12 Executive Committee) ──────
EXPECTED_CAPTION_LINES = 4629
EXPECTED_TURN_COUNT = 286
EXPECTED_ATTRIBUTION_COUNTS = {
    None: 139,          # 115 left bare + 24 later filled by the DB-side voice map
    "macro": 72,
    "recognition": 24,
    "alternation": 49,
    "self_intro": 2,
}


@pytest.fixture(scope="module")
def vtt_text() -> str:
    return VTT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lines(vtt_text: str) -> list[CaptionLine]:
    return parse_vtt(vtt_text)


@pytest.fixture(scope="module")
def timeline() -> dict:
    return json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def speeches(lines, timeline):
    """Collapse exactly as the ingest pipeline does — panel lookup attached."""
    return collapse_cc_turns(lines, panel_owner_at=make_panel_owner_lookup(timeline))


def turn(speeches, sequence: int):
    """Sequence numbers are 1-based positions in the collapse output."""
    return speeches[sequence - 1]


# ── 1. parse_vtt ────────────────────────────────────────────────────


def test_parse_vtt_line_count_in_sane_range(lines):
    assert 4000 <= len(lines) <= 5500


def test_parse_vtt_line_count_pinned(lines):
    assert len(lines) == EXPECTED_CAPTION_LINES


def test_parse_vtt_unescapes_html_entities(lines):
    # Broadcast CC encodes the '>>' turn marker as '&gt;&gt;'. If the unescape
    # regresses, every turn marker disappears and the whole meeting collapses
    # into one speech.
    assert not any("&gt;" in line.text for line in lines)
    assert not any("&amp;" in line.text for line in lines)


def test_parse_vtt_preserves_turn_markers(lines):
    markers = [line for line in lines if line.text.lstrip().startswith(">>")]
    assert len(markers) == EXPECTED_TURN_COUNT


def test_parse_vtt_strips_cue_markup_and_timestamps(lines):
    assert not any("<c>" in line.text or "-->" in line.text for line in lines)
    assert all(line.text.strip() == line.text for line in lines)


def test_parse_vtt_lines_are_time_ordered(lines):
    starts = [line.start_seconds for line in lines]
    assert starts == sorted(starts)


def test_track_is_detected_as_broadcast_cc(lines):
    assert looks_like_cc_turn_captions(lines) is True


# ── 2. collapse_cc_turns: full-meeting invariants ───────────────────


def test_turn_count_matches_db(speeches):
    assert len(speeches) == EXPECTED_TURN_COUNT


def test_attribution_kind_counts_pinned(speeches):
    counts = collections.Counter(s.attribution for s in speeches)
    assert dict(counts) == EXPECTED_ATTRIBUTION_COUNTS


def test_attributed_turns_are_named_and_bare_turns_are_not(speeches):
    for i, s in enumerate(speeches, start=1):
        if s.attribution is None:
            assert s.speaker_name_raw == "UNATTRIBUTED", f"seq {i}"
            assert s.speaker_role is None, f"seq {i}"
        else:
            assert s.speaker_name_raw != "UNATTRIBUTED", f"seq {i}"


def test_panel_timeline_contributes_nothing_on_this_meeting(lines, timeline):
    """The panel opener requires an independent in-block anchor before it is
    trusted; on this meeting every panel-opened block fails that guard, so the
    panel lookup must not change a single turn. This pins the guard, not the
    absence of a timeline — the fixture timeline has 51 intervals."""
    assert len(timeline["intervals"]) == 51
    with_panel = collapse_cc_turns(lines, panel_owner_at=make_panel_owner_lookup(timeline))
    without_panel = collapse_cc_turns(lines, panel_owner_at=None)
    assert [(s.speaker_name_raw, s.attribution) for s in with_panel] == [
        (s.speaker_name_raw, s.attribution) for s in without_panel
    ]
    assert not any(s.attribution == "panel" for s in with_panel)


def test_speech_timings_are_monotonic_and_bounded(speeches):
    starts = [s.start_seconds for s in speeches]
    assert starts == sorted(starts)
    assert all(s.end_seconds >= s.start_seconds for s in speeches)


# ── 3. Known-speaker spot assertions ────────────────────────────────

MACRO_PINS = [
    (2, "Mayor", "Andrew Knack"),
    (10, "Clerk", "The Clerk"),
    (29, "Clerk", "The Clerk"),
    (202, "Mayor", "Andrew Knack"),
    (214, "Mayor", "Andrew Knack"),
    (233, "Mayor", "Andrew Knack"),
    (245, "Mayor", "Andrew Knack"),
    # A mis-fired steno macro: the Windsor mayor's name macro lands in an
    # Edmonton meeting. Pinned as current behaviour — collapse trusts the
    # macro, and cleaning it up is a roster-resolution concern, not a
    # collapse concern.
    (267, "Mayor", "Drew Dilkens"),
]

RECOGNITION_PINS = [
    (3, "STEVENSON"),
    (203, "TANG"),      # chair's seq 202 ends '...Councillor Tang?'
    (215, "PARMAR"),
    (234, "STEVENSON"),  # chair's seq 233 ends '...Councillor Stevenson has questions?'
    (246, "SALVADOR"),
    (264, "PARMAR"),
]

ALTERNATION_PINS = [
    (205, "TANG"), (207, "TANG"), (209, "TANG"), (211, "TANG"), (213, "TANG"),
    (230, "PARMAR"), (232, "PARMAR"),
    (236, "STEVENSON"), (238, "STEVENSON"), (240, "STEVENSON"), (242, "STEVENSON"),
    (249, "SALVADOR"), (251, "SALVADOR"), (253, "SALVADOR"), (255, "SALVADOR"),
]

UNATTRIBUTED_PINS = [
    1,                        # captioning disclaimer preamble
    5,                        # roll-call, chair not macro'd
    204, 206, 208, 210, 212,  # staff answers inside the TANG block
    235, 237, 239, 241,       # staff answers inside the STEVENSON block
    286,                      # meeting tail
]


@pytest.mark.parametrize("sequence,role,name", MACRO_PINS)
def test_macro_turns(speeches, sequence, role, name):
    s = turn(speeches, sequence)
    assert (s.attribution, s.speaker_role, s.speaker_name_raw) == ("macro", role, name)


@pytest.mark.parametrize("sequence,surname", RECOGNITION_PINS)
def test_recognition_turns(speeches, sequence, surname):
    s = turn(speeches, sequence)
    assert (s.attribution, s.speaker_name_raw) == ("recognition", surname)
    assert s.speaker_role in ("Councillor", "Mayor")


@pytest.mark.parametrize("sequence,surname", ALTERNATION_PINS)
def test_alternation_turns(speeches, sequence, surname):
    s = turn(speeches, sequence)
    assert (s.attribution, s.speaker_name_raw) == ("alternation", surname)


@pytest.mark.parametrize("sequence", UNATTRIBUTED_PINS)
def test_unattributed_turns(speeches, sequence):
    s = turn(speeches, sequence)
    assert s.attribution is None
    assert s.speaker_name_raw == "UNATTRIBUTED"


def test_relay_guard_keeps_third_party_greeting_unattributed(speeches):
    """seq 6 is 'And good morning from Councillor Wright.' — someone relaying a
    remote member's greeting, not Wright speaking. Without the guard the chair's
    preceding recognition would credit this turn to the wrong member."""
    s = turn(speeches, 6)
    assert "FROM COUNCILLOR WRIGHT" in s.text.upper()
    assert s.attribution is None
    assert s.speaker_name_raw == "UNATTRIBUTED"


def test_chair_prompt_block_phase_is_not_inverted(speeches):
    """The 248-262 block: the chair's short un-macro'd prompts ('Thank you. Do
    you have a motion please go ahead.') are 'chair' anchors that reset the
    alternation phase. Before that anchor class existed the phase inverted and
    credited the chair's prompts to Salvador. Odd sequences are Salvador, even
    sequences stay bare."""
    for sequence in (249, 251, 253, 255):
        s = turn(speeches, sequence)
        assert (s.attribution, s.speaker_name_raw) == ("alternation", "SALVADOR"), sequence
    for sequence in (248, 250, 252, 254):
        s = turn(speeches, sequence)
        assert s.attribution is None, sequence
        assert s.speaker_name_raw == "UNATTRIBUTED", sequence
    assert turn(speeches, 248).text.upper().startswith("THANK YOU. DO YOU HAVE A MOTION")


def test_self_intro_turns(speeches):
    for sequence, name in ((43, "Tom Mansfield"), (44, "Todd James")):
        s = turn(speeches, sequence)
        assert (s.attribution, s.speaker_name_raw) == ("self_intro", name), sequence


# ── 4. _cc_recognized_speaker grammar cases ─────────────────────────


@pytest.mark.parametrize("tail,expected", [
    # Accepted: name mid-tail followed by an invitation clause.
    ("JUST CHECKING, COUNCILLOR SALVADOR, DO YOU HAVE QUESTIONS?",
     ("Councillor", "SALVADOR")),
    ("THANK YOU, COUNCILLOR SALVADOR, IF YOU WANT TO PUT THE MOTION ON THE FLOOR",
     ("Councillor", "SALVADOR")),
    ("ALL RIGHT, COUNCILLOR STEVENSON, GO AHEAD.", ("Councillor", "STEVENSON")),
    ("ALL RIGHT, COUNCILLOR STEVENSON HAS QUESTIONS?", ("Councillor", "STEVENSON")),
    # Accepted: bare trailing mention. Queue readouts name several — the
    # LAST-named speaks first.
    ("COUNCILLOR WRIGHT, COUNCILLOR PARMAR.", ("Councillor", "PARMAR")),
    ("GOOD MORNING. COUNCILLOR RUTHERFORD.", ("Councillor", "RUTHERFORD")),
    # COUNSELLOR is a recurring live-steno spelling; role normalises.
    ("COUNSELLOR TANG.", ("Councillor", "TANG")),
    # Rejected: turn-closers, motion attributions, bare references.
    ("THANK YOU, COUNCILLOR PAQUETTE.", None),
    ("SORRY, COUNCILLOR TANG.", None),
    ("SECONDED BY COUNCILLOR PARMAR.", None),
    ("MOVED BY COUNCILLOR SALVADOR.", None),
    ("COUNCILLOR TANG IS YES.", None),
    ("THANK YOU, MAYOR KNACK.", None),
    ("NO NAMES HERE AT ALL.", None),
])
def test_cc_recognized_speaker(tail, expected):
    assert _cc_recognized_speaker(tail) == expected


# ── 5. truecase_caption_text ────────────────────────────────────────


@pytest.fixture(scope="module")
def proper() -> dict[str, str]:
    """Static proper nouns plus a stand-in roster (loaded from the DB at runtime)."""
    d = dict(_STATIC_PROPER)
    d.update({"knack": "Knack", "salvador": "Salvador", "tang": "Tang"})
    return d


@pytest.mark.parametrize("raw,expected", [
    ("GOOD MORNING. WE'LL CALL THIS MEETING TO ORDER.",
     "Good morning. We'll call this meeting to order."),
    # 'a.m.' must not terminate the sentence.
    ("IT IS 9:31 A.M. AND WE ARE READY TO BEGIN.",
     "It is 9:31 a.m. and we are ready to begin."),
    # Role before a roster-cased name reads as a title.
    ("THANK YOU, COUNCILLOR SALVADOR. GO AHEAD.",
     "Thank you, Councillor Salvador. Go ahead."),
    # Already mixed-case (auto-captions / macro labels) passes through untouched.
    ("This is already Mixed Case text.", "This is already Mixed Case text."),
    # A trailing period on a number is a decimal point, not a sentence end.
    ("WE HAVE 20 APPLICATIONS AND 3.1 MILLION DOLLARS.",
     "We have 20 applications and 3.1 million dollars."),
])
def test_truecase_caption_text(raw, expected, proper):
    assert truecase_caption_text(raw, proper) == expected


def test_truecase_capitalises_standalone_i(proper):
    assert truecase_caption_text("I THINK I'M OUT OF TIME.", proper) == "I think I'm out of time."


# ── 6. Self-introduction capture ────────────────────────────────────


def collapse_one(body: str):
    return collapse_cc_turns([CaptionLine(10.0, 12.0, ">> " + body)])[0]


def test_self_intro_names_the_turn():
    s = collapse_one("MY NAME IS LISA DRURY AND TODAY I WILL PRESENT THE REPORT.")
    assert (s.speaker_name_raw, s.attribution) == ("Lisa Drury", "self_intro")
    assert s.speaker_role is None  # members of the public must not be roster-matched


def test_self_intro_stops_before_trailing_title():
    s = collapse_one(
        "GOOD MORNING. MY NAME IS KRISTINE ARCHIBALD EXECUTIVE DIRECTOR OF THE SOCIETY."
    )
    assert s.speaker_name_raw == "Kristine Archibald"
    assert "Executive" not in s.speaker_name_raw


# ── 7. make_panel_owner_lookup ──────────────────────────────────────


SYNTHETIC_TIMELINE = {
    "intervals": [
        {"state": "speaking", "name": "Ashley Salvador", "start": 100.0, "end": 200.0},
        {"state": "armed", "name": "Keren Tang", "start": 300.0, "end": 400.0},
    ]
}


@pytest.mark.parametrize("probe_start,expected", [
    # Probed at start+8s against an interval with a 5s leading margin, so a turn
    # starting at 97.0 probes 105.0 — exactly the interval's armed edge.
    (97.0, "SALVADOR"),
    (96.9, None),      # 104.9 — inside the leading margin
    (150.0, "SALVADOR"),
    (191.9, "SALVADOR"),  # 199.9 — just inside the trailing edge
    (192.1, None),     # 200.1 — past the interval
    (250.0, None),     # gap between intervals
    (295.0, None),     # 'armed' intervals never own the floor
])
def test_panel_owner_lookup(probe_start, expected):
    lookup = make_panel_owner_lookup(SYNTHETIC_TIMELINE)
    assert lookup(probe_start) == expected


def test_panel_owner_lookup_returns_none_without_usable_timeline():
    assert make_panel_owner_lookup(None) is None
    assert make_panel_owner_lookup({}) is None
    assert make_panel_owner_lookup({"intervals": []}) is None
    # No 'speaking' intervals at all — nothing to attribute from.
    assert make_panel_owner_lookup(
        {"intervals": [{"state": "armed", "name": "Keren Tang", "start": 1.0, "end": 2.0}]}
    ) is None


def test_panel_owner_lookup_returns_surname_upper():
    lookup = make_panel_owner_lookup(SYNTHETIC_TIMELINE)
    assert lookup(150.0) == "SALVADOR"  # 'Ashley Salvador' → surname, upper-cased
