"""SAM mask rasters and the on-sidewalk measure used by the agent's ``get_track``.

Mask layout (protocol/sam3.md in github.com/meta-models/meta-sam): ``data=H,W,payload``
where the raster covers the record's box, inclusive on both ends (a box
x1=10..x2=14 has W=5), row-major, 1 = object. The payload is arithmetic-coded
base85, so it is decoded with Meta's own ``meta_sam_parser.decode_mask_to_raster``
rather than a reimplementation.

On-sidewalk measure: an object blocks the walkway only if it stands on it. For
each column of the object's mask, the lowest object pixel is where it meets the
ground; the measure is the fraction of those ground-contact points that fall
inside the union of the ``sidewalk`` masks on the same frame (checking a few
pixels below the contact point, since the contact sits on the object/ground edge).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .sam_parse import MaskToken, SamRecord

_MARKER = {"lossless": "~", "one_bit": "!"}
CONTACT_SLACK_PX = 4


def decode_raster(mask: MaskToken, cache_dir: Path | None = None) -> np.ndarray:
    """(H, W) uint8 raster of 0/1 for one mask token. Decoding is slow for large
    masks (a 1024x574 sidewalk mask takes ~5 s), so with ``cache_dir`` each decoded
    raster is kept as a bit-packed .npy keyed by the payload hash."""
    key = hashlib.sha1(f"{mask.encoding}{mask.width}x{mask.height}{mask.data}".encode()).hexdigest()[:20]
    path = Path(cache_dir) / f"{key}.npy" if cache_dir else None
    if path is not None and path.exists():
        bits = np.load(path)
        return np.unpackbits(bits)[: mask.height * mask.width].reshape(mask.height, mask.width)
    raster = _decode(mask)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, np.packbits(raster))
    return raster


def _decode(mask: MaskToken) -> np.ndarray:
    try:
        from meta_sam_parser import SegmentationMask, decode_mask_to_raster
    except ImportError as e:
        raise RuntimeError(
            "mask decoding needs Meta's parser: pip install meta-sam-parser==0.1.0 "
            "(listed in environment.yml)"
        ) from e
    # The decoder wants the payload exactly as SAM sent it, marker included
    # (sam_parse stores the marker separately as ``encoding``).
    payload = _MARKER[mask.encoding] + mask.data
    flat = decode_mask_to_raster(
        SegmentationMask(encoding=mask.encoding, payload=payload, width=mask.width, height=mask.height)
    )
    return np.frombuffer(flat, dtype=np.uint8).reshape(mask.height, mask.width)


def ground_contacts(rec: SamRecord, raster: np.ndarray) -> list[tuple[int, int]]:
    """Frame (x, y) of the lowest object pixel in each mask column."""
    pts = []
    rows = np.arange(raster.shape[0])
    for c in range(raster.shape[1]):
        col = raster[:, c]
        if col.any():
            pts.append((rec.x1 + c, rec.y1 + int(rows[col > 0].max())))
    return pts


def _union(frame_w: int, frame_h: int, layers: list[tuple[SamRecord, np.ndarray]]) -> np.ndarray:
    canvas = np.zeros((frame_h, frame_w), dtype=np.uint8)
    for rec, r in layers:
        h = min(r.shape[0], frame_h - rec.y1)
        w = min(r.shape[1], frame_w - rec.x1)
        canvas[rec.y1:rec.y1 + h, rec.x1:rec.x1 + w] |= r[:h, :w]
    return canvas


def on_sidewalk_fraction(
    obj: tuple[SamRecord, np.ndarray], sidewalks: list[tuple[SamRecord, np.ndarray]]
) -> float | None:
    """Share of the object's ground-contact points inside a sidewalk mask, or
    None when there is no sidewalk mask on this frame (unknown, not zero)."""
    if not sidewalks:
        return None
    rec, raster = obj
    contacts = ground_contacts(rec, raster)
    if not contacts:
        return None
    walk = _union(rec.frame_w, rec.frame_h, sidewalks)
    inside = 0
    for x, y in contacts:
        y2 = min(rec.frame_h, y + CONTACT_SLACK_PX + 1)
        if walk[y:y2, x].any():
            inside += 1
    return round(inside / len(contacts), 2)
