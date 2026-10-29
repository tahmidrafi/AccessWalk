"""rules.yaml + citation validator tests. No network, no video."""
from accesswalk.inventory import Inventory, build_tracks
from accesswalk.phrases import SAM_PHRASES
from accesswalk.rules import load_rules
from accesswalk.sam_parse import SamRecord
from accesswalk.validator import Rejection, finalize, validate_citation
from test_inventory import _meta


def _rec(f, oid, x1=100, y1=100, x2=300, y2=300) -> SamRecord:
    return SamRecord(frame_index=f, object_id=oid, x1=x1, y1=y1, x2=x2, y2=y2,
                     frame_w=720, frame_h=1280, box_conf=0.8)


def _inv():
    m = _meta()
    tracks = build_tracks("raised sidewalk slab", [_rec(f, 0) for f in range(10, 15)], m)
    tracks += build_tracks("car", [_rec(f, 0, 500, 0, 700, 100) for f in range(0, 5)], m)
    tracks += build_tracks("handrail", [_rec(f, 0) for f in range(20, 25)], m)
    return m, Inventory(video_sha256="abc", tracks=tracks, duplicates={})


def _req(**kw) -> dict:
    base = dict(check_id="surface_damage", track_id="raised-sidewalk-slab-0", frame_index=12,
                severity="high", confidence=0.8, title="Heaved slab",
                evidence_note="Slab edge lifted well above its neighbour beside the tree.")
    return {**base, **kw}


def test_rules_cover_all_checks_and_phrase_list_unchanged():
    rules = load_rules()
    assert len(rules.checks) == 8
    assert sorted(SAM_PHRASES) == sorted([
        "trash bin", "car", "pole", "raised sidewalk slab", "curb", "tactile paving", "sidewalk",
        "stairs", "handrail", "doorknob", "overgrown vegetation", "license plate",
    ])  # the cached d4 batch; changing this list means new SAM spend


def test_valid_citation_copies_sam_box_and_rule_fields():
    m, inv = _inv()
    f = validate_citation(_req(), inv, m, load_rules())
    assert not isinstance(f, Rejection)
    assert (f.bbox.x1, f.bbox.y2, f.frame_ms) == (100, 300, 2400)
    assert f.verify_manually is True and f.reference.startswith("2010 ADA Standards 303")


def test_rejections_explain_what_to_fix():
    m, inv = _inv()
    rules = load_rules()
    cases = {
        "unknown check_id": _req(check_id="ada_violation"),
        "not in this clip": _req(track_id="trash-bin-7"),
        "must cite a track of": _req(track_id="car-0", frame_index=2),
        "has no box on frame 30": _req(frame_index=30),
        "not allowed": _req(evidence_note="This slab is an ADA violation and must be fixed now."),
        "related tracks": _req(related_track_ids=["tree-root-0"]),
        "bad arguments": _req(confidence=1.4),
    }
    for reason, raw in cases.items():
        r = validate_citation(raw, inv, m, rules)
        assert isinstance(r, Rejection) and reason in r.reason, (reason, r)


def test_keyframe_check_cites_anchor_track():
    m, inv = _inv()  # steps_without_ramp may cite a handrail track (ramps are judged from frames)
    f = validate_citation(_req(check_id="steps_without_ramp", track_id="handrail-0", frame_index=22,
                               severity="medium"), inv, m, load_rules())
    assert not isinstance(f, Rejection)


def test_finalize_merges_and_numbers_in_time_order():
    m, inv = _inv()
    rules = load_rules()
    a = validate_citation(_req(frame_index=11, confidence=0.6), inv, m, rules)
    b = validate_citation(_req(frame_index=13, confidence=0.9), inv, m, rules)
    c = validate_citation(_req(check_id="missing_handrail", track_id="handrail-0", frame_index=20,
                               severity="low"), inv, m, rules)
    out = finalize([c, a, b])
    assert [(f.finding_id, f.frame_index) for f in out] == [("f1", 13), ("f2", 20)]
