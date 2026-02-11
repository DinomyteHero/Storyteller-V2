import random

from backend.app.core.mechanics_resolver import CheckConfig, resolve_check


def test_resolve_check_deterministic_seeded_rng():
    rng = random.Random(7)
    out = resolve_check(CheckConfig(skill="slice", dc=12, base_mod=2), rng=rng)
    assert out.check is not None
    assert out.check.skill == "slice"
    assert out.check.dc == 12
    assert out.check.roll == 11
    assert out.category in {"PARTIAL", "SUCCESS", "FAIL", "CRIT_SUCCESS", "CRIT_FAIL"}
