from backend.app.core.truth_ledger import contradiction_errors


def test_contradiction_errors_detect_mismatch():
    errs = contradiction_errors({"ally_alive": False}, {"ally_alive": True})
    assert errs
    assert "Contradiction" in errs[0]


def test_contradiction_errors_flags_immutable_as_canon_violation():
    errs = contradiction_errors(
        {"canon_event_abc": "retconned"},
        {"canon_event_abc": "0 BBY: Death Star destroyed"},
        immutable_facts={"canon_event_abc": True},
        historical_lore_label="established Star Wars Legends lore",
    )
    assert errs
    assert "CANON VIOLATION" in errs[0]
