"""Smoke test for the agent hosts (d5-agentloop). Approved budget ~$0.02.

Per host (baseten, fireworks; same open-weight model), at most 2 + 2 calls:
  1. text: "reply ok" at temperature 0          (retried once without temperature if refused)
  2. image + one tool + parallel_tool_calls     (if refused, retried once with only the image,
                                                 to tell image support from tool-param support)
The image is a face- and plate-blurred keyframe from clip 1 (data/cache/.../frames),
downscaled to 512 px wide. Reports per host: accepted settings, usage, cost, model served.
All calls go through llm.chat (cache + usage.jsonl). No closed-model fallback.

Run:  micromamba run -n accesswalk python scripts/smoke_llm.py
"""
import base64
import json
import sys
from pathlib import Path

import cv2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / ".env")

from accesswalk import llm  # noqa: E402

CLIP_SHA = "64c947d94556e94b8acf6c7cfeacc2fdda80ae42632657ab5e0eb06e407f7ae7"  # PXL_20261027_211833467
FRAME = REPO_ROOT / "data" / "cache" / CLIP_SHA / "frames" / "60.jpg"  # rendered keyframe (blurred)
TOOL = [{"type": "function", "function": {
    "name": "report_surface", "description": "Report whether the walkway surface looks damaged.",
    "parameters": {"type": "object", "properties": {"damaged": {"type": "boolean"},
                                                    "reason": {"type": "string"}},
                   "required": ["damaged", "reason"]}}}]


def _image_url() -> str:
    img = cv2.imread(str(FRAME))
    if img is None:
        raise SystemExit(f"missing {FRAME}; run scripts/run_inventory.py first")
    h, w = img.shape[:2]
    img = cv2.resize(img, (512, round(h * 512 / w)))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _try(host: str, messages: list, tools: list | None, params: dict) -> tuple[llm.ChatResult | None, str]:
    try:
        return llm.chat(messages, video_sha256=CLIP_SHA, tools=tools, params=params, order=(host,),
                        tag="smoke"), ""
    except RuntimeError as e:
        return None, str(e)[:300]


def smoke(host: str, image_url: str) -> dict:
    out: dict = {"host": host, "calls": []}

    def record(name: str, res: llm.ChatResult | None, err: str, params: dict) -> None:
        row = {"call": name, "params": params, "ok": res is not None}
        if res is None:
            row["error"] = err
        else:
            msg = res.message
            row.update(model_served=res.model_served, usage=res.usage, cost_usd=round(res.cost_usd, 5),
                       cache_hit=res.cache_hit, finish_reason=res.finish_reason,
                       content=(msg.get("content") or "")[:160],
                       tool_calls=[c["function"]["name"] + " " + c["function"].get("arguments", "")[:120]
                                   for c in msg.get("tool_calls") or []])
        out["calls"].append(row)

    text = [{"role": "user", "content": "Reply with the single word: ok"}]
    p = {"temperature": 0, "max_tokens": 2000}
    res, err = _try(host, text, None, p)
    record("text t=0", res, err, p)
    out["temperature_0"] = res is not None
    if res is None:
        p2 = {"max_tokens": 2000}
        res, err = _try(host, text, None, p2)
        record("text default temp", res, err, p2)

    vision = [{"role": "user", "content": [
        {"type": "text", "text": "This is a frame from a sidewalk walking video. Look at the walkway "
                                 "surface, then call report_surface."},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]}]
    p = {"temperature": 0, "max_tokens": 4000, "parallel_tool_calls": True}
    res, err = _try(host, vision, TOOL, p)
    record("image+tools t=0", res, err, p)
    out["image_with_tools"] = res is not None
    out["image"] = res is not None
    if res is None:
        p2 = {"max_tokens": 4000}
        res, err = _try(host, vision[:1], None, p2)
        record("image only", res, err, p2)
        out["image"] = res is not None
    out["cost_usd"] = round(sum(c.get("cost_usd", 0) for c in out["calls"]), 5)
    return out


def main() -> int:
    url = _image_url()
    results = [smoke(h, url) for h in llm.OPEN_PROVIDERS]
    print(json.dumps(results, indent=2))
    for r in results:
        print(f"{r['host']}: temperature 0 {'accepted' if r['temperature_0'] else 'REFUSED'} | "
              f"image {'accepted' if r['image'] else 'REFUSED'} | "
              f"image+tools+parallel {'accepted' if r['image_with_tools'] else 'REFUSED'} | "
              f"cost ${r['cost_usd']:.5f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
