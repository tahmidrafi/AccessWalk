"""Parser for SAM 3.1 video segmentation ``output_text``.

Grammar (per dev.meta.ai/docs/sam/reading-segmentation, verified Oct 28 2026):

  * The stream is one "line" per frame, each introduced by a frame marker
    ``<Nf>`` where ``N`` is the **zero-based** frame index. Indices are not
    necessarily contiguous or ascending, and a frame on which no object is
    visible emits no line, so do not assume the k-th line is frame k.
  * Within a frame, records are comma-separated. A record is::

        <object_id><|box;x1=..;y1=..;x2=..;y2=..;w=<frameW>;h=<frameH>[;c=<conf>]|><|mask;x=..;y=..[;c=<conf>];data=<H>,<W>,<marker>payload|>

    The object id is a bare integer, stable across frames. The box comes first,
    then the mask. Box coordinates are **source pixels**; ``w``/``h`` repeat the
    source frame dimensions on every record.
  * Mask ``data`` is ``<H>,<W>,<marker>payload`` where ``H``/``W`` are the mask
    raster's rows/cols and the marker is ``~`` (lossless) or ``!`` (one_bit).
    The payload is base85 (not base64). We preserve it verbatim; decoding to a
    raster is deferred to the official ``meta-sam-parser`` when overlays are
    built (base85 is not specified fully enough to reimplement safely).

Tokenizing is safe because ``|`` (0x7C) is outside the base85 payload charset,
so ``|>`` always closes a token and ``<|box`` / ``<|mask`` always open one, even
though payloads may contain ``,``, ``<`` and ``>``.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

_FRAME_RE = re.compile(r"<(\d+)f>")
# id immediately precedes <|box...|>; mask (also starting <| ... |>) is optional.
_RECORD_RE = re.compile(
    r"(?P<id>\d+)<\|box;(?P<box>[^|]*)\|>(?:<\|mask;(?P<mask>[^|]*)\|>)?"
)

_ENC_MARKER = {"~": "lossless", "!": "one_bit"}


class MaskToken(BaseModel):
    height: int  # mask raster rows
    width: int  # mask raster cols
    encoding: str  # "lossless" | "one_bit"
    data: str  # base85 payload, verbatim (undecoded)


class SamRecord(BaseModel):
    frame_index: int  # zero-based, as read from <Nf>
    object_id: int  # ordinal, stable across frames within one request
    x1: int
    y1: int
    x2: int
    y2: int
    frame_w: int  # source frame dimensions (box coord space)
    frame_h: int
    box_conf: float | None = None
    mask_conf: float | None = None
    mask: MaskToken | None = None


def _kv(fields: str) -> dict[str, str]:
    """Parse ``a=1;b=2`` into a dict. The mask ``data`` value may contain commas
    but never a ``;``, so splitting on ``;`` is safe."""
    out: dict[str, str] = {}
    for part in fields.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k] = v
    return out


def _parse_mask(mask_fields: str) -> tuple[MaskToken | None, float | None]:
    kv = _kv(mask_fields)
    conf = float(kv["c"]) if "c" in kv else None
    data = kv.get("data")
    if not data:
        return None, conf
    h_str, w_str, rest = data.split(",", 2)
    marker = rest[:1]
    return (
        MaskToken(
            height=int(h_str),
            width=int(w_str),
            encoding=_ENC_MARKER.get(marker, marker),
            data=rest[1:],
        ),
        conf,
    )


def parse_output(output_text: str) -> list[SamRecord]:
    """Parse the full (accumulated) ``output_text`` into flat records.

    Empty input returns ``[]`` (a valid result meaning zero matches)."""
    records: list[SamRecord] = []
    if not output_text or not output_text.strip():
        return records

    # Split into (frame_index, body) segments on the frame markers.
    markers = list(_FRAME_RE.finditer(output_text))
    for i, m in enumerate(markers):
        frame_index = int(m.group(1))
        body_start = m.end()
        body_end = markers[i + 1].start() if i + 1 < len(markers) else len(output_text)
        body = output_text[body_start:body_end]
        for rec in _RECORD_RE.finditer(body):
            box = _kv(rec.group("box"))
            mask_token, mask_conf = (None, None)
            if rec.group("mask") is not None:
                mask_token, mask_conf = _parse_mask(rec.group("mask"))
            records.append(
                SamRecord(
                    frame_index=frame_index,
                    object_id=int(rec.group("id")),
                    x1=int(box["x1"]),
                    y1=int(box["y1"]),
                    x2=int(box["x2"]),
                    y2=int(box["y2"]),
                    frame_w=int(box["w"]),
                    frame_h=int(box["h"]),
                    box_conf=float(box["c"]) if "c" in box else None,
                    mask_conf=mask_conf,
                    mask=mask_token,
                )
            )
    return records


def to_tracks(records: list[SamRecord]) -> dict[int, list[SamRecord]]:
    """Group records by ``object_id``, each list sorted by ``frame_index``.

    One request segments a single noun phrase, so object ids are the distinct
    tracked instances of that phrase."""
    tracks: dict[int, list[SamRecord]] = {}
    for r in records:
        tracks.setdefault(r.object_id, []).append(r)
    for recs in tracks.values():
        recs.sort(key=lambda r: r.frame_index)
    return tracks
