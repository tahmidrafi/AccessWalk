"""Plate-blur plan: interpolation between 5 fps SAM boxes, holds, gaps, padding. No video."""
from accesswalk.ingest import IngestMeta, SourceMeta, StreamMeta
from accesswalk.plates import plate_plan, proxy_times_ms
from accesswalk.schemas import Track, TrackBox


def _track(*boxes) -> Track:
    tbs = [TrackBox(frame_index=ms // 200, frame_ms=ms, x1=x, y1=y, x2=x + 50, y2=y + 20, conf=0.9)
           for ms, x, y in boxes]
    return Track(track_id="license-plate-0", phrase="license plate", object_id=0, first_ms=tbs[0].frame_ms,
                 last_ms=tbs[-1].frame_ms, n_frames=len(tbs), mean_conf=0.9,
                 keyframe_index=tbs[0].frame_index, keyframe_ms=tbs[0].frame_ms, boxes=tbs)


def _plan(track, times, **kw):
    return plate_plan([track], times, 720, 1280, pad=0.0, **kw)


def test_box_between_sam_frames_is_interpolated():
    t = _track((1000, 100, 100), (1200, 200, 300))
    (x1, y1, _, _), = _plan(t, [1100])[0]
    assert (x1, y1) == (150 - 6, 200 - 6)  # midpoint, minus the small-box padding floor


def test_ends_hold_for_a_short_time_only():
    t = _track((1000, 100, 100), (1200, 110, 100))
    plan = _plan(t, [500, 700, 1500, 1700], hold_ms=400)
    assert sorted(plan) == [1, 2]  # 300 ms outside is held, 500 ms is not


def test_long_gap_is_not_bridged_but_both_sides_hold():
    t = _track((1000, 100, 100), (4000, 500, 100))
    plan = _plan(t, [1200, 2500, 3800], max_gap_ms=1000, hold_ms=400)
    assert sorted(plan) == [0, 2]
    assert plan[0][0][0] == 100 - 6 and plan[2][0][0] == 500 - 6


def test_padding_scales_and_clamps_to_the_frame():
    t = _track((1000, 700, 0))
    (x1, y1, x2, y2), = plate_plan([t], [1000], 720, 1280, pad=0.2)[0]
    assert (x1, y1) == (700 - 10, 0)
    assert x2 == 720 and y2 > 20  # clamped on the right, padded below


def test_two_tracks_on_one_frame_both_blur():
    a, b = _track((1000, 100, 100)), _track((1000, 300, 300))
    assert len(plate_plan([a, b], [1000], 720, 1280)[0]) == 2


def test_proxy_times_account_for_the_sam_frame_showing_the_scene_late():
    def meta(fps):
        return IngestMeta(
            video_sha256="a", ingest_version=1, created_at="now",
            source=SourceMeta(filename="x.mp4", coded_width=1920, coded_height=1080, rotation=-90,
                              display_width=1080, display_height=1920, fps=fps, duration_s=1.0,
                              has_audio=False),
            sam=StreamMeta(width=720, height=1280, fps=5.0, n_frames=5),
            proxy=StreamMeta(width=720, height=1280, fps=fps, n_frames=30),
            frame_ms=[0, 200, 400, 600, 800], faces_frames=0, faces_boxes=0,
        )
    assert proxy_times_ms(meta(29.997))[8] == 200  # measured: SAM frame 1 is proxy frame 8
    assert proxy_times_ms(meta(24.0))[6] == 167  # 2 frames late at 24 fps too: last before 300 ms is 7
