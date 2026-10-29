"""Unit tests for the face-blur box geometry (detections_to_boxes). No video.

This is the risky part of ingest: a detection runs on a downscaled frame, and the
box must be scaled back to full resolution, padded, and clipped before blurring.
The test clip had zero faces, so this logic is otherwise unexercised -- and a bug
here would leak faces in the public d4 clips."""
import numpy as np
from accesswalk.ingest import detections_to_boxes, plan_blur_boxes


def _faces(*rows) -> np.ndarray:
    """Build an Nx15 YuNet-style detection array (only the first 4 cols matter)."""
    arr = np.zeros((len(rows), 15), dtype=np.float32)
    for i, (x, y, w, h) in enumerate(rows):
        arr[i, :4] = (x, y, w, h)
    return arr


def test_scale_back_to_full_res():
    # detection on a 2x-downscaled frame -> inv=2.0 doubles coords
    boxes = detections_to_boxes(_faces((100, 100, 50, 50)), inv=2.0, pad=0.0, w=2000, h=2000)
    assert boxes == [(200, 200, 300, 300)]


def test_padding_applied():
    boxes = detections_to_boxes(_faces((100, 100, 100, 100)), inv=1.0, pad=0.2, w=2000, h=2000)
    assert boxes == [(80, 80, 220, 220)]  # 20% of 100 = 20 px each side


def test_clipped_to_frame_bounds():
    # near top-left and near bottom-right, big pad -> clipped to [0,w]/[0,h]
    boxes = detections_to_boxes(
        _faces((10, 10, 100, 100), (1900, 1900, 100, 100)), inv=1.0, pad=0.5, w=2000, h=2000
    )
    assert boxes[0] == (0, 0, 160, 160)
    assert boxes[1] == (1850, 1850, 2000, 2000)


def test_none_and_degenerate():
    assert detections_to_boxes(None, inv=1.0, pad=0.2, w=100, h=100) == []
    # zero-area detection produces no box
    assert detections_to_boxes(_faces((50, 50, 0, 0)), inv=1.0, pad=0.0, w=100, h=100) == []


def test_plan_holds_each_detection():
    plan = plan_blur_boxes({10: [(0, 0, 10, 10)]}, n_frames=100, hold=4, max_gap=30)
    assert sorted(plan) == list(range(6, 15))


def test_plan_bridges_gap_with_hull():
    # same face drifting right, detected at 0 and 17 only (the campus-clip pattern)
    a, b = (100, 100, 130, 130), (160, 110, 190, 140)
    plan = plan_blur_boxes({0: [a], 17: [b]}, n_frames=100, hold=4, max_gap=30)
    assert all(k in plan for k in range(0, 22))  # no unblurred frame in between
    assert (100, 100, 190, 140) in plan[9]


def test_plan_no_bridge_past_max_gap_or_between_far_faces():
    a = (0, 0, 10, 10)
    plan = plan_blur_boxes({0: [a], 50: [a]}, n_frames=100, hold=4, max_gap=30)
    assert 25 not in plan
    far = (900, 900, 910, 910)
    plan = plan_blur_boxes({0: [a], 10: [far]}, n_frames=100, hold=2, max_gap=30)
    assert 5 not in plan


def test_frame_sized_false_positive_dropped():
    # the clip-1 false positive: ~800x1200 "face" on a 1080-wide frame
    faces = _faces((20, 500, 800, 1200), (500, 300, 60, 70))
    assert detections_to_boxes(faces, inv=1.0, pad=0.0, w=1080, h=1920) == [(500, 300, 560, 370)]
