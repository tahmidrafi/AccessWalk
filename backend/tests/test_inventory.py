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


def test_mask_png_is_full_frame_with_transparent_background():
    import numpy as np
    from accesswalk.inventory import mask_png
    rec = _rec(0, 0, 10, 20, 14, 24)
    raster = np.zeros((5, 5), dtype=np.uint8)
    raster[1:4, 1:4] = 1
    img = mask_png(rec, raster)
    assert img.shape == (1280, 720, 4)               # sam.mp4 size, BGRA
    assert img[:, :, 3].sum() == 9 * 255              # only the 3x3 object is opaque
    assert tuple(img[22, 12]) == (255, 255, 255, 255) and img[20, 10, 3] == 0


def test_review_masks_cover_get_track_samples_and_predecode_skips_cached(tmp_path, monkeypatch):
    import numpy as np
    from accesswalk import masks
    from accesswalk.inventory import review_masks
    from accesswalk.sam_parse import MaskToken

    m = _meta()
    def tok(s):
        return MaskToken(encoding="one_bit", width=2, height=1, data=s)
    obj = [_rec(f, 0, 0, 0, 10, 10).model_copy(update={"mask": tok(f"o{f}")}) for f in range(3)]
    walk = _rec(1, 0, 0, 0, 10, 10).model_copy(update={"mask": tok("w1")})
    other = _rec(30, 0, 0, 0, 10, 10).model_copy(update={"mask": tok("w30")})
    records = {"trash bin": obj, "sidewalk": [walk, other]}
    tracks = build_tracks("trash bin", obj, m) + build_tracks("sidewalk", [walk, other], m)
    tokens = review_masks(tracks, records)
    assert {t.data for t in tokens} == {"o0", "o1", "o2", "w1"}  # no sidewalk mask off the sampled frames

    calls = []
    monkeypatch.setattr(masks, "_decode", lambda t: calls.append(t.data) or np.zeros((1, 2), "uint8"))
    assert masks.predecode(tokens, tmp_path) == 4
    assert masks.predecode(tokens, tmp_path) == 0
    calls.clear()
    masks.decode_raster(tokens[0], tmp_path)
    assert calls == []  # review reads it back, no decode
