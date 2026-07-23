from app.domain.enums import Verdict
from app.sources.user_verification.scoring import recompute_trust


def test_empty_defaults_to_half():
    assert recompute_trust([]) == 0.5


def test_all_available_is_one():
    assert recompute_trust([(Verdict.AVAILABLE, 1.0), (Verdict.AVAILABLE, 1.0)]) == 1.0


def test_mixed_weighted():
    score = recompute_trust([(Verdict.AVAILABLE, 3.0), (Verdict.SOLD_OUT, 1.0)])
    assert score == 0.75
