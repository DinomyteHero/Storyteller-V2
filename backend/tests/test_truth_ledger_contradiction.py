from backend.app.core.truth_ledger import contradiction_errors


def test_contradiction_errors_detect_mismatch():
    errs = contradiction_errors({"ally_alive": False}, {"ally_alive": True})
    assert errs
    assert "Contradiction" in errs[0]
