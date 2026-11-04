"""Does Muse Spark Open on Baseten accept video input? One tiny request per content-part
shape, on a 4 s, 360p, 2 fps cut of the demo clip's published proxy.mp4 (faces and
plates blurred, metadata stripped). Every call is logged to usage.jsonl.

  micromamba run -n accesswalk python scripts/probe_baseten_video.py <clip_stem>

Result Nov 3 (demo clip, 8-12 s): video_url accepted, steps and house door described
correctly, 530 prompt tokens, $0.0023; an "input_video" part is refused (400).
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
load_dotenv(REPO / ".env")
from accesswalk import llm, usage  # noqa: E402
from openai import OpenAI  # noqa: E402

clip = sys.argv[1]
rep = json.loads((REPO / "data" / "out" / "eval_runs" / "v1" / f"{clip}.json").read_text(encoding="utf-8"))
sha = rep["video"]["video_sha256"]
proxy = REPO / "data" / "cache" / sha / "proxy.mp4"
assert proxy.name == "proxy.mp4" and "raw" not in proxy.parts
out = REPO / "data" / "out" / "probe_clip.mp4"  # git-ignored
subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", "8", "-t", "4", "-i", str(proxy),
                "-vf", "fps=2,scale=-2:360", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-map_metadata", "-1", str(out)], check=True)
url = "data:video/mp4;base64," + base64.b64encode(out.read_bytes()).decode()
print(f"clip {out.stat().st_size} bytes")

p = llm.providers_from_env()["baseten"]
client = OpenAI(api_key=os.environ[p.api_key_env], base_url=p.base_url)
question = {"type": "text", "text": "In one sentence: what is in this video, and does it show steps?"}
shapes = {
    "video_url": {"type": "video_url", "video_url": {"url": url}},
    "input_video": {"type": "input_video", "input_video": {"url": url}},
}
for name, part in shapes.items():
    try:
        r = client.chat.completions.create(model=p.model, max_tokens=3000, temperature=0,
                                           messages=[{"role": "user", "content": [part, question]}])
        u = r.usage.model_dump() if r.usage else {}
        cost = llm.cost_usd("baseten", u)
        usage.log_call(usage.UsageRecord(provider="baseten", model_requested=p.model, model_served=r.model,
                                         usage=u, cost_usd=cost, video_sha256=sha,
                                         extra={"tag": "probe-video", "shape": name}))
        print(f"{name}: OK model={r.model} usage={u} cost=${cost:.4f}")
        print("   content:", (r.choices[0].message.content or "")[:300].replace("\n", " "))
    except Exception as e:  # report the host's answer as is
        print(f"{name}: {type(e).__name__} status={getattr(e, 'status_code', None)} {str(e)[:400]}")
