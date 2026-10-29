"""SAM 3.1 video segmentation client (Meta Model API, Responses protocol).

One short noun phrase per request. The video is uploaded once via the Files API
and referenced by ``file_id`` on subsequent phrases. Only the derived ``sam.mp4``
may be uploaded -- never a raw clip (which still carries GPS and unblurred faces).

Pricing: $0.20 / 1,000 video frames, minimum 50 frames billed per request
(see CLAUDE.md "Meta API facts"). ``usage.video_frames_processed`` reports the
billed frames in the response.

Caching and usage logging wrap this module in ``usage.py``; this file only does
the network calls and the cost arithmetic.
"""
from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI

MODEL = "sam-3.1"
PRICE_PER_1K_FRAMES = 0.20
MIN_BILLED_FRAMES = 50


def billed_frames(n_frames: int) -> int:
    """Frames billed for one request: at least the 50-frame minimum."""
    return max(MIN_BILLED_FRAMES, int(n_frames))


def estimate_cost(n_frames: int, n_phrases: int) -> float:
    """USD to run ``n_phrases`` noun phrases over a clip of ``n_frames`` frames."""
    return n_phrases * billed_frames(n_frames) * PRICE_PER_1K_FRAMES / 1000.0


def make_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    key = api_key or os.environ["MODEL_API_KEY"]
    url = base_url or os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
    return OpenAI(api_key=key, base_url=url)


def upload_sam_video(client: OpenAI, sam_mp4: str | Path) -> str:
    """Upload the derived ``sam.mp4`` via the Files API; return its ``file_id``.

    Refuses anything not named ``sam.mp4`` so a raw clip can never be uploaded."""
    path = Path(sam_mp4)
    if path.name != "sam.mp4":
        raise ValueError(
            f"refusing to upload {path.name!r}: only the derived sam.mp4 may be sent to SAM "
            "(raw clips carry GPS and unblurred faces)"
        )
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as f:
        up = client.files.create(purpose="user_data", file=f)
    return up.id


def segment_phrase(
    client: OpenAI,
    file_id: str,
    phrase: str,
    mask_encoding: str = "one_bit",
) -> tuple[str, dict, str | None]:
    """Segment one noun ``phrase`` against an uploaded video.

    Returns ``(output_text, usage, model_served)`` where ``output_text`` is the
    accumulated special-token text (parse it with ``sam_parse.parse_output``),
    ``usage`` is the response usage dict (includes ``video_frames_processed``), and
    ``model_served`` is the model id the response reports. Streaming is the
    recommended path for video."""
    req = dict(
        model=MODEL,
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": phrase},
                    {"type": "input_video", "file_id": file_id},
                ],
            }
        ],
        metadata={"mask_encoding": mask_encoding},
    )
    chunks: list[str] = []
    with client.responses.stream(**req) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                chunks.append(event.delta)
        final = stream.get_final_response()

    text = "".join(chunks)
    if not text:  # fall back to the assembled final response if no deltas were seen
        text = getattr(final, "output_text", "") or ""
    usage = {}
    if getattr(final, "usage", None) is not None:
        usage = final.usage.model_dump() if hasattr(final.usage, "model_dump") else dict(final.usage)
    return text, usage, getattr(final, "model", None)
