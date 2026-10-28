"""Smoke test: tools on PATH, keys present, Meta Model API and Baseten reachable.

Run:  micromamba run -n accesswalk python scripts/check_setup.py
Cost: Meta call is a free model listing; Baseten call is a ~10-token completion.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ok = True


def report(name, passed, detail=""):
    global ok
    ok &= passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def mask(key):
    return f"{key[:4]}...{key[-4:]}" if key and len(key) > 8 else "(missing)"


# 1. Tools
report("python", sys.version_info[:2] == (3, 11), sys.version.split()[0])
for tool, args in [("ffmpeg", ["-hide_banner", "-version"]), ("node", ["--version"])]:
    path = shutil.which(tool)
    if not path:
        report(tool, False, "not on PATH")
        continue
    out = subprocess.run([path, *args], capture_output=True, text=True).stdout.splitlines()[0]
    report(tool, True, f"{out}  ({path})")

# 2. Meta Model API (free: list models)
meta_key = os.getenv("MODEL_API_KEY", "").strip()
report("MODEL_API_KEY set", bool(meta_key), mask(meta_key))
if meta_key:
    try:
        meta = OpenAI(base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"), api_key=meta_key)
        ids = {m.id for m in meta.models.list().data}
        for needed in ["sam-3.1", "muse-spark-1.3", "muse-voice-transcribe-1.0"]:
            report(f"Meta model {needed}", needed in ids)
    except Exception as e:  # noqa: BLE001
        report("Meta Model API", False, repr(e)[:200])

# 3. Baseten / Muse Spark Open (tiny completion)
bt_key = os.getenv("BASETEN_API_KEY", "").strip()
report("BASETEN_API_KEY set", bool(bt_key), mask(bt_key))
if bt_key:
    try:
        bt = OpenAI(base_url=os.getenv("BASETEN_BASE_URL", "https://inference.baseten.co/v1"), api_key=bt_key)
        r = bt.chat.completions.create(
            model=os.getenv("BASETEN_MODEL", "meta-models/muse-spark-open-1026"),
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=10,
        )
        report("Baseten muse-spark-open-1026", True, repr(r.choices[0].message.content))
    except Exception as e:  # noqa: BLE001
        report("Baseten muse-spark-open-1026", False, repr(e)[:200])

print("\nALL GOOD" if ok else "\nSome checks failed - see above.")
sys.exit(0 if ok else 1)
