"""Annotation format tests: range checks, scoring helpers, committed files valid. No network."""
import pytest
from accesswalk.annotations import ANNOTATIONS_DIR, ClipAnnotation, load_all
from pydantic import ValidationError


def _ann(**kw) -> ClipAnnotation:
    base = dict(
        clip="c", annotator="t", status="done", duration_s=20.0,
        barriers=[{"check": "surface_damage", "t": [10.0, 12.0], "sev": "high", "note": "slab"}],
        clean=[[0.0, 5.0]], not_applicable=["round_doorknob"],
    )
    return ClipAnnotation.model_validate({**base, **kw})


def test_matching_and_false_positives():
    a = _ann()
    assert a.matches("surface_damage", 12_500) == [0]      # within the 1 s tolerance
    assert a.matches("surface_damage", 13_500) == []
    assert a.matches("narrow_passage", 11_000) == []        # wrong check
    assert a.is_false_positive("surface_damage", 3_000)     # in a clean range
    assert a.is_false_positive("round_doorknob", 11_000)    # not applicable
    assert not a.is_false_positive("surface_damage", 7_000)  # unlabelled: not scored


@pytest.mark.parametrize(
    "kw, msg",
    [
        ({"clean": [[9.0, 11.0]]}, "overlaps barrier"),
        ({"clean": [[5.0, 25.0]]}, "not inside"),
        ({"not_applicable": ["surface_damage"]}, "not_applicable"),
        ({"barriers": [{"check": "violation", "t": [1, 2], "sev": "high", "note": "x"}]}, "check"),
    ],
)
def test_bad_annotations_rejected(kw, msg):
    with pytest.raises(ValidationError, match=msg):
        _ann(**kw)


def test_committed_annotations_are_valid():
    all_files = load_all(ANNOTATIONS_DIR, done_only=False)
    assert "PXL_20261027_211833467" in all_files
