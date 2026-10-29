"""Inventory: turn per-phrase SAM records into the object list the agent reasons over.

Steps (``build_inventory``):
  1. stitch: SAM can give one object a new id after it leaves the frame or is
     occluded; ids whose tracks meet end-to-start (gap <= 1 s) at overlapping
     boxes are merged (``stitch_ids``).
  2. tracks: one ``Track`` per object. One SAM request = one noun phrase, so
     ``object_id`` is only unique within that phrase; ``track_id`` =
     ``<phrase-slug>-<object_id>`` is unique per report.
  3. dedupe: the same object found by two phrases ("raised sidewalk slab" and
     "cracked pavement") is flagged, keeping the more confident track
     (``find_duplicates``). Duplicates stay in the report, so citations still
     resolve, but the agent sees each object once.
  4. evidence frames: each kept track's keyframe is rendered from the
     face-blurred ``sam.mp4`` to ``frames/<i>.jpg`` with license plates (SAM
     ``license plate`` tracks) blurred too, since report frames are published.

Keyframe choice: the frame where the object is most confidently seen, tie-broken
by box area (bigger = closer to the camera = more legible evidence), ignoring
boxes clipped by the frame edge when an unclipped one exists.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np
from pydantic import BaseModel

from . import masks
from .ingest import DEFAULT_OUT_ROOT, IngestMeta
from .phrases import PLATE_PHRASE
from .sam_parse import SamRecord, to_tracks
from .schemas import BBox, Track, TrackBox


def phrase_slug(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-")


def _touches_edge(r: SamRecord, margin: int = 2) -> bool:
    return r.x1 <= margin or r.y1 <= margin or r.x2 >= r.frame_w - margin or r.y2 >= r.frame_h - margin


def _keyframe(recs: list[SamRecord]) -> SamRecord:
    inside = [r for r in recs if not _touches_edge(r)] or recs
    return max(inside, key=lambda r: (r.box_conf or 0.0, (r.x2 - r.x1) * (r.y2 - r.y1)))


def build_tracks(phrase: str, records: list[SamRecord], meta: IngestMeta) -> list[Track]:
    tracks: list[Track] = []
    for object_id, recs in sorted(to_tracks(records).items()):
        key = _keyframe(recs)
        confs = [r.box_conf for r in recs if r.box_conf is not None]
        tracks.append(
            Track(
                track_id=f"{phrase_slug(phrase)}-{object_id}",
                phrase=phrase,
                object_id=object_id,
                first_ms=meta.frame_ms[recs[0].frame_index],
                last_ms=meta.frame_ms[recs[-1].frame_index],
                n_frames=len(recs),
                mean_conf=round(sum(confs) / len(confs), 3) if confs else None,
                keyframe_index=key.frame_index,
                keyframe_ms=meta.frame_ms[key.frame_index],
                boxes=[
                    TrackBox(
                        frame_index=r.frame_index, frame_ms=meta.frame_ms[r.frame_index],
                        x1=r.x1, y1=r.y1, x2=r.x2, y2=r.y2, conf=r.box_conf,
                    )
                    for r in recs
                ],
            )
        )
    return tracks


def _iou(a: BBox | SamRecord, b: BBox | SamRecord) -> float:
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
    return inter / union if union > 0 else 0.0


def stitch_ids(records: list[SamRecord], max_gap: int = 5, min_iou: float = 0.3) -> list[SamRecord]:
    """Merge object ids of one phrase whose tracks continue each other: B starts
    after A ends, within ``max_gap`` frames, with A's last box overlapping B's
    first. Returns records with B's ``object_id`` rewritten to A's."""
    tracks = to_tracks(records)
    order = sorted(tracks, key=lambda i: tracks[i][0].frame_index)
    alias: dict[int, int] = {}
    tail: dict[int, SamRecord] = {}  # root id -> last record of the merged track
    for oid in order:
        head = tracks[oid][0]
        candidates = [
            (_iou(last, head), root)
            for root, last in tail.items()
            if 0 < head.frame_index - last.frame_index <= max_gap and _iou(last, head) >= min_iou
        ]
        root = max(candidates)[1] if candidates else oid
        alias[oid] = root
        tail[root] = tracks[oid][-1]
    return [r.model_copy(update={"object_id": alias[r.object_id]}) for r in records]


def find_duplicates(tracks: list[Track], min_iou: float = 0.6, min_shared: float = 0.5) -> dict[str, str]:
    """Map duplicate track_id -> kept track_id for tracks of different phrases
    that box the same object: mean IoU >= ``min_iou`` over shared frames, and
    shared frames >= ``min_shared`` of the shorter track. Keeps the higher
    mean_conf (then longer) track."""
    rank = sorted(tracks, key=lambda t: (t.mean_conf or 0.0, t.n_frames), reverse=True)
    boxes = {t.track_id: {b.frame_index: b for b in t.boxes} for t in tracks}
    dup: dict[str, str] = {}
    for i, keep in enumerate(rank):
        if keep.track_id in dup:
            continue
        for other in rank[i + 1:]:
            if other.track_id in dup or other.phrase == keep.phrase:
                continue
            a, b = boxes[keep.track_id], boxes[other.track_id]
            shared = a.keys() & b.keys()
            if not shared or len(shared) < min_shared * min(keep.n_frames, other.n_frames):
                continue
            if sum(_iou(a[f], b[f]) for f in shared) / len(shared) >= min_iou:
                dup[other.track_id] = keep.track_id
    return dup


def render_frames(
    meta: IngestMeta,
    frame_indices: set[int],
    plate_tracks: list[Track],
    out_root: str | Path = DEFAULT_OUT_ROOT,
    pad: float = 0.3,
) -> dict[int, Path]:
    """Write ``frames/<i>.jpg`` from the face-blurred ``sam.mp4``, blurring any
    plate box on that frame. Returns frame_index -> path."""
    clip_dir = Path(out_root) / meta.video_sha256
    out_dir = clip_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    plates: dict[int, list[TrackBox]] = {}
    for t in plate_tracks:
        for b in t.boxes:
            plates.setdefault(b.frame_index, []).append(b)
    written: dict[int, Path] = {}
    cap = cv2.VideoCapture(str(clip_dir / "sam.mp4"))
    try:
        i = 0
        while frame_indices - written.keys():
            ok, frame = cap.read()
            if not ok:
                break
            if i in frame_indices:
                h, w = frame.shape[:2]
                for b in plates.get(i, []):
                    px, py = int((b.x2 - b.x1) * pad), int((b.y2 - b.y1) * pad)
                    x1, y1 = max(0, b.x1 - px), max(0, b.y1 - py)
                    x2, y2 = min(w, b.x2 + px), min(h, b.y2 + py)
                    if x2 > x1 and y2 > y1:
                        k = max(15, (min(x2 - x1, y2 - y1) // 2) | 1)
                        frame[y1:y2, x1:x2] = cv2.GaussianBlur(frame[y1:y2, x1:x2], (k, k), 0)
                path = out_dir / f"{i}.jpg"
                cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
                written[i] = path
            i += 1
    finally:
        cap.release()
    missing = frame_indices - written.keys()
    if missing:
        raise RuntimeError(f"sam.mp4 ended before frames {sorted(missing)[:5]}")
    return written


def mask_png(rec: SamRecord, raster: np.ndarray) -> np.ndarray:
    """Full-frame BGRA image (sam.mp4 size, e.g. 720x1280): white where the object
    is, fully transparent elsewhere. The report overlay reads only the alpha."""
    out = np.zeros((rec.frame_h, rec.frame_w, 4), dtype=np.uint8)
    h = min(raster.shape[0], rec.frame_h - rec.y1)
    w = min(raster.shape[1], rec.frame_w - rec.x1)
    on = raster[:h, :w].astype(bool)
    region = out[rec.y1:rec.y1 + h, rec.x1:rec.x1 + w]
    region[on] = (255, 255, 255, 255)
    return out


def render_masks(
    meta: IngestMeta, tracks: list[Track], records_by_phrase: dict[str, list[SamRecord]],
    out_root: str | Path = DEFAULT_OUT_ROOT,
) -> dict[str, str]:
    """Keyframe mask PNG per track -> ``masks/<track_id>_f<i>.png``. Returns track_id -> URL."""
    clip_dir = Path(out_root) / meta.video_sha256
    urls: dict[str, str] = {}
    for t in tracks:
        rec = next((r for r in records_by_phrase.get(t.phrase, [])
                    if r.object_id == t.object_id and r.frame_index == t.keyframe_index), None)
        if rec is None or rec.mask is None:
            continue
        name = f"{t.track_id}_f{t.keyframe_index}.png"
        path = clip_dir / "masks" / name
        if not path.exists():
            raster = masks.decode_raster(rec.mask, clip_dir / "masks")
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), mask_png(rec, raster))
        urls[t.track_id] = f"/media/{meta.video_sha256}/masks/{name}"
    return urls


class Inventory(BaseModel):
    video_sha256: str
    tracks: list[Track]  # every non-plate track, duplicates included
    duplicates: dict[str, str]  # duplicate track_id -> kept track_id

    def kept(self) -> list[Track]:
        """What the agent sees: one track per object."""
        return [t for t in self.tracks if t.track_id not in self.duplicates]


def build_inventory(
    meta: IngestMeta,
    records_by_phrase: dict[str, list[SamRecord]],
    out_root: str | Path = DEFAULT_OUT_ROOT,
    render: bool = True,
) -> Inventory:
    tracks: list[Track] = []
    plate_tracks: list[Track] = []
    stitched = {phrase: stitch_ids(records) for phrase, records in records_by_phrase.items()}
    for phrase, records in stitched.items():
        built = build_tracks(phrase, records, meta)
        (plate_tracks if phrase == PLATE_PHRASE else tracks).extend(built)
    inv = Inventory(video_sha256=meta.video_sha256, tracks=tracks, duplicates=find_duplicates(tracks))
    if render:
        frames = render_frames(meta, {t.keyframe_index for t in inv.kept()}, plate_tracks, out_root)
        for t in inv.tracks:
            if t.keyframe_index in frames:
                t.keyframe_url = f"/media/{meta.video_sha256}/frames/{t.keyframe_index}.jpg"
        mask_urls = render_masks(meta, inv.kept(), stitched, out_root)
        for t in inv.tracks:
            t.mask_url = mask_urls.get(t.track_id)
        (Path(out_root) / meta.video_sha256 / "inventory.json").write_text(inv.model_dump_json(indent=2))
    return inv
