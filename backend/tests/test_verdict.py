"""Route verdict from synthetic findings."""

from accesswalk.schemas import BBox, Finding
from accesswalk.verdict import route_verdict


def _f(
    fid="f1", sev="medium", conf=0.8, ms=5000, title="Bin on the sidewalk", verify=True, tag=None
) -> Finding:
    return Finding(
        finding_id=fid,
        check_id="sidewalk_obstruction",
        title=title,
        severity=sev,
        confidence=conf,
        track_id="t",
        frame_index=0,
        frame_ms=ms,
        bbox=BBox(x1=0, y1=0, x2=1, y2=1),
        evidence_note="evidence",
        location_tag=tag,
        verify_manually=verify,
    )


def test_no_findings_on_a_finished_review_is_clear():
    v = route_verdict([])
    assert v.rating == "no_likely_barriers" and v.key_finding_ids == []


def test_no_findings_on_an_unfinished_review_is_never_clear():
    v = route_verdict([], complete=False)
    assert v.rating == "caution" and "not been fully checked" in v.summary


def test_one_confident_high_blocks_the_whole_route():
    v = route_verdict([_f("f1", "low"), _f("f2", "high", ms=20000, title="Steps"), _f("f3", "low", ms=30000)])
    assert v.rating == "likely_blocked" and v.key_finding_ids[0] == "f2"
    assert "20 s in" in v.summary and "Steps" in v.summary


def test_a_doubtful_high_only_cautions():
    v = route_verdict([_f(sev="high", conf=0.49)])
    assert v.rating == "caution"


def test_block_threshold_is_inclusive():
    assert route_verdict([_f(sev="high", conf=0.5)]).rating == "likely_blocked"


def test_many_mediums_stay_caution():
    fs = [_f(f"f{i}", "medium", ms=i * 1000) for i in range(1, 7)]
    v = route_verdict(fs)
    assert v.rating == "caution" and len(v.key_finding_ids) == 3


def test_key_findings_rank_blocking_then_severity_then_confidence():
    fs = [_f("low", "low", 0.9), _f("doubt", "high", 0.3), _f("med", "medium", 0.9), _f("block", "high", 0.6)]
    assert route_verdict(fs).key_finding_ids == ["block", "doubt", "med"]


def test_blocking_lead_names_the_earliest_blocker():
    fs = [_f("late", "high", 0.99, ms=30000, title="Late"), _f("early", "high", 0.6, ms=10000, title="Early")]
    v = route_verdict(fs)
    assert "Early" in v.summary and "10 s in" in v.summary and v.key_finding_ids[0] == "late"


def test_location_tag_and_verify_wording():
    v = route_verdict([_f(sev="high", tag="bus stop")])
    assert "bus stop" in v.summary and "judged from video" in v.summary
    assert "judged from video" not in route_verdict([_f(verify=False)]).summary


def test_agent_summary_follows_the_lead_and_obeys_the_wording_rules():
    assert route_verdict([_f()], "Mostly smooth.").summary.endswith("Mostly smooth.")
    assert "violation" not in route_verdict([_f()], "A clear ADA violation here.").summary
    assert "red box" not in route_verdict([_f()], "The bin in the red box is large.").summary


def test_unfinished_with_findings_says_there_may_be_more():
    v = route_verdict([_f(sev="high")], complete=False)
    assert v.rating == "likely_blocked" and "may be more" in v.summary


def test_never_says_violation_in_any_lead():
    for fs in ([], [_f()], [_f(sev="high")]):
        for complete in (True, False):
            assert "violation" not in route_verdict(fs, complete=complete).summary.lower()
