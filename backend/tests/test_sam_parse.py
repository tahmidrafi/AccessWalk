"""Unit tests for the SAM output parser. No network.

The fixture uses the documented grammar and the docs' example box/mask header
(dev.meta.ai/docs/sam/reading-segmentation). The docs' mask payload is elided
with "...", so the fixture completes it with short payloads that deliberately
contain ',' and '>' to exercise the tokenizer. After the first real SAM run
(d3-samfirst) a trimmed real response should be added as a second fixture and
diffed against the official meta-sam-parser.
"""
from pathlib import Path

from accesswalk.sam_parse import MaskToken, SamRecord, parse_output, to_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "sam_output_example.txt"


def _parse_fixture() -> list[SamRecord]:
    return parse_output(FIXTURE.read_text())


def test_empty_output_is_zero_matches():
    assert parse_output("") == []
    assert parse_output("   \n  ") == []


def test_record_count_and_frames():
    recs = _parse_fixture()
    assert len(recs) == 3
    # Frame indices come from the <Nf> markers, not line position: 0, 0, then 2.
    assert [r.frame_index for r in recs] == [0, 0, 2]


def test_box_fields_and_confidence():
    r = _parse_fixture()[0]
    assert (r.frame_index, r.object_id) == (0, 0)
    assert (r.x1, r.y1, r.x2, r.y2) == (211, 228, 270, 254)
    assert (r.frame_w, r.frame_h) == (320, 334)  # box coord space = source pixels
    assert r.box_conf == 0.97


def test_mask_encoding_and_payload_with_commas_and_gt():
    r = _parse_fixture()[0]
    assert isinstance(r.mask, MaskToken)
    assert (r.mask.height, r.mask.width) == (27, 60)
    assert r.mask.encoding == "lossless"  # '~' marker
    # payload is preserved verbatim, including ',' and '>' that live in base85
    assert r.mask.data == "ab,c>d"


def test_one_bit_mask_and_mask_confidence():
    r = _parse_fixture()[1]
    assert (r.object_id, r.x1, r.y1, r.x2, r.y2) == (1, 10, 20, 40, 60)
    assert r.mask.encoding == "one_bit"  # '!' marker
    assert r.mask.data == "xyz"
    assert r.mask_conf == 0.80


def test_to_tracks_groups_and_sorts():
    tracks = to_tracks(_parse_fixture())
    assert set(tracks) == {0, 1}
    assert [r.frame_index for r in tracks[0]] == [0, 2]  # sorted, non-contiguous
    assert [r.frame_index for r in tracks[1]] == [0]


def test_box_only_record_has_no_mask():
    recs = parse_output("<3f>0<|box;x1=1;y1=2;x2=3;y2=4;w=320;h=334|>")
    assert len(recs) == 1
    assert recs[0].mask is None
    assert recs[0].frame_index == 3


def test_multiple_objects_same_frame():
    recs = _parse_fixture()
    frame0 = [r for r in recs if r.frame_index == 0]
    assert sorted(r.object_id for r in frame0) == [0, 1]
