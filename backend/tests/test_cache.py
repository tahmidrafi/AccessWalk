"""Unit tests for the SAM cache + usage logging. No network.

The real network call (``sam.segment_phrase``) is injected via ``segment_fn`` so
the cache logic is exercised without openai or the API."""
import pytest
from accesswalk import cache, usage
from accesswalk.ingest import IngestMeta, SourceMeta, StreamMeta

SAM_TEXT = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=320;h=334|>"


def _meta(sha="deadbeef", ingest_version=1) -> IngestMeta:
    return IngestMeta(
        video_sha256=sha,
        ingest_version=ingest_version,
        created_at="2026-10-28T00:00:00+00:00",
        source=SourceMeta(
            filename="x.mp4", coded_width=1920, coded_height=1080, rotation=-90,
            display_width=1080, display_height=1920, fps=30.0, duration_s=22.2, has_audio=True,
        ),
        sam=StreamMeta(width=720, height=1280, fps=5.0, n_frames=111),
        proxy=StreamMeta(width=720, height=1280, fps=30.0, n_frames=0),
        frame_ms=[0, 200],
        faces_frames=0,
        faces_boxes=0,
    )


def _good_segment(_client, _file_id, _phrase, mask_encoding="one_bit", include_confidence=True):
    return SAM_TEXT, {"video_frames_processed": 111}, "sam-3.1"


def _boom(*a, **k):  # must never be called on a cache hit
    raise AssertionError("network/upload should not be called")


def test_usage_logger_roundtrip(tmp_path):
    log = tmp_path / "usage.jsonl"
    usage.log_call(usage.UsageRecord(provider="meta", model_requested="sam-3.1", cost_usd=0.5), path=log)
    usage.log_call(usage.UsageRecord(provider="baseten", model_requested="muse", cost_usd=0.25), path=log)
    recs = usage.read_log(log)
    assert [r.provider for r in recs] == ["meta", "baseten"]
    assert usage.total_cost(log) == 0.75


def test_cache_miss_writes_and_logs(tmp_path):
    log = tmp_path / "usage.jsonl"
    res = cache.segment_cached(
        None, _meta(), "tree root", out_root=tmp_path, usage_log=log,
        segment_fn=_good_segment, upload_fn=lambda c, p: "file-x",
    )
    assert res.cache_hit is False
    assert res.file_id == "file-x"
    assert len(res.records) == 1
    assert res.cost_usd == pytest.approx(111 * 0.20 / 1000)
    # raw response cached under <sha>/sam/<key>.json
    assert cache.cache_path(tmp_path, "deadbeef", res.cache_key).exists()
    rec = usage.read_log(log)[0]
    assert rec.cache_hit is False and rec.phrase == "tree root" and rec.model_served == "sam-3.1"


def test_cache_hit_skips_network(tmp_path):
    log = tmp_path / "usage.jsonl"
    cache.segment_cached(
        None, _meta(), "tree root", out_root=tmp_path, usage_log=log,
        segment_fn=_good_segment, upload_fn=lambda c, p: "file-x",
    )
    # second call: segment_fn and upload_fn would raise if invoked
    res = cache.segment_cached(
        None, _meta(), "tree root", out_root=tmp_path, usage_log=log,
        segment_fn=_boom, upload_fn=_boom,
    )
    assert res.cache_hit is True
    assert res.cost_usd == 0.0
    assert len(res.records) == 1
    assert len(usage.read_log(log)) == 2  # both calls logged


def test_incomplete_stream_is_not_cached(tmp_path):
    log = tmp_path / "usage.jsonl"

    def _no_usage(_c, _f, _p, mask_encoding="one_bit", include_confidence=True):
        return "", {}, None  # no usage -> incomplete

    with pytest.raises(RuntimeError):
        cache.segment_cached(
            None, _meta(), "handrail", out_root=tmp_path, usage_log=log,
            segment_fn=_no_usage, upload_fn=lambda c, p: "file-x",
        )
    md = {"mask_encoding": "one_bit", "include_confidence": "true"}
    key = cache.cache_key("sam-3.1", "handrail", md, 1, 5.0, 720, 1280)
    assert not cache.cache_path(tmp_path, "deadbeef", key).exists()


def test_ingest_version_changes_key():
    md = {"mask_encoding": "one_bit", "include_confidence": "true"}
    assert cache.cache_key("sam-3.1", "x", md, 1, 5.0, 720, 1280) != \
        cache.cache_key("sam-3.1", "x", md, 2, 5.0, 720, 1280)


def test_request_metadata_changes_key():
    conf = {"mask_encoding": "one_bit", "include_confidence": "true"}
    noconf = {"mask_encoding": "one_bit", "include_confidence": "false"}
    assert cache.cache_key("sam-3.1", "x", conf, 1, 5.0, 720, 1280) != \
        cache.cache_key("sam-3.1", "x", noconf, 1, 5.0, 720, 1280)
