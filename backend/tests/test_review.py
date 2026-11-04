"""Review-stage selection. No network."""
import pytest
from accesswalk import review


def test_default_review_exists_and_env_overrides(monkeypatch):
    monkeypatch.delenv("ACCESSWALK_REVIEW", raising=False)
    assert review.selected() == review.DEFAULT_REVIEW in review.REVIEWS
    monkeypatch.setenv("ACCESSWALK_REVIEW", "open")
    assert review.selected() == "open"
    monkeypatch.setenv("ACCESSWALK_REVIEW", "nope")
    with pytest.raises(ValueError, match="ACCESSWALK_REVIEW"):
        review.selected()
