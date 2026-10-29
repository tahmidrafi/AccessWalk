"""Inventory: turn per-phrase SAM records into report ``Track`` objects.

One SAM request = one noun phrase, so ``object_id`` is only unique within that
phrase. ``track_id`` = ``<phrase-slug>-<object_id>`` makes it unique per report.

Keyframe choice: the frame where the object is most confidently seen, tie-broken
by box area (bigger = closer to the camera = more legible evidence), ignoring
boxes clipped by the frame edge when an unclipped one exists.
"""
from __future__ import annotations

import re

from .ingest import IngestMeta
from .sam_parse import SamRecord, to_tracks
from .schemas import Track, TrackBox


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
