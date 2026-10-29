"""Inventory tests: track building, id stitching, cross-phrase dedupe. No video."""
from accesswalk.ingest import IngestMeta, SourceMeta, StreamMeta
from accesswalk.inventory import build_tracks, find_duplicates, phrase_slug, stitch_ids
from accesswalk.sam_parse import SamRecord


def _meta(n=40) -> IngestMeta:
    return IngestMeta(
        video_sha256="abc", ingest_version=1, created_at="now",
        source=SourceMeta(filename="x.mp4", coded_width=1920, coded_height=1080, rotation=-90,
                          display_width=1080, display_height=1920, fps=30.0, duration_s=8.0,
                          has_audio=False),
        sam=StreamMeta(width=720, height=1280, fps=5.0, n_frames=n),
        proxy=StreamMeta(width=720, height=1280, fps=30.0, n_frames=6 * n),
        frame_ms=[i * 200 for i in range(n)], faces_frames=0, faces_boxes=0,
    )


def _rec(f, oid, x1, y1, x2, y2, c=0.8) -> SamRecord:
    return SamRecord(frame_index=f, object_id=oid, x1=x1, y1=y1, x2=x2, y2=y2,
                     frame_w=720, frame_h=1280, box_conf=c)


def test_build_tracks_keyframe_prefers_unclipped_confident_box():
    recs = [_rec(0, 0, 0, 100, 200, 300, c=0.95),   # touches left edge
            _rec(1, 0, 50, 100, 250, 300, c=0.85),
            _rec(2, 0, 60, 100, 200, 260, c=0.85)]  # same conf, smaller
    (t,) = build_tracks("trash bin", recs, _meta())
    assert t.track_id == "trash-bin-0"
    assert (t.keyframe_index, t.keyframe_ms, t.first_ms, t.last_ms) == (1, 200, 0, 400)
    assert t.mean_conf == 0.883


def test_phrase_slug():
    assert phrase_slug("Raised  sidewalk slab!") == "raised-sidewalk-slab"


def test_stitch_merges_continuation_only():
    recs = [_rec(f, 0, 100, 100, 200, 200) for f in range(0, 5)]
    recs += [_rec(f, 3, 110, 105, 210, 205) for f in range(7, 10)]   # same object, new id
    recs += [_rec(f, 4, 500, 900, 600, 1000) for f in range(7, 10)]  # elsewhere: separate
    recs += [_rec(f, 5, 100, 100, 200, 200) for f in range(30, 32)]  # too late: separate
    ids = {r.frame_index: r.object_id for r in stitch_ids(recs) if r.x1 < 300}
    assert ids[8] == 0 and ids[30] == 5
    assert {r.object_id for r in stitch_ids(recs) if r.x1 >= 500} == {4}


def test_duplicates_across_phrases_keep_more_confident():
    m = _meta()
    slab = build_tracks("raised sidewalk slab", [_rec(f, 0, 100, 100, 300, 300, 0.8) for f in range(5)], m)
    crack = build_tracks("cracked pavement", [_rec(f, 0, 105, 100, 300, 310, 0.7) for f in range(5)], m)
    bin_ = build_tracks("trash bin", [_rec(f, 0, 500, 500, 600, 700, 0.9) for f in range(5)], m)
    other_slab = build_tracks(
        "raised sidewalk slab", [_rec(f, 1, 100, 100, 300, 300, 0.6) for f in range(5)], m
    )
    dup = find_duplicates(slab + crack + bin_ + other_slab)
    assert dup == {"cracked-pavement-0": "raised-sidewalk-slab-0"}  # same phrase never merged
