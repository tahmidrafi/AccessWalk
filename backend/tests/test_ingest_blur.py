"""Unit tests for the face-blur box geometry (detections_to_boxes). No video.

This is the risky part of ingest: a detection runs on a downscaled frame, and the
box must be scaled back to full resolution, padded, and clipped before blurring.
The test clip had zero faces, so this logic is otherwise unexercised -- and a bug
here would leak faces in the public d4 clips."""
import numpy as np
from accesswalk.ingest import detections_to_boxes


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
