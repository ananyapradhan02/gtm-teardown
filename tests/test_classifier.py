"""Core classifier behaviour (happy paths)."""

from gtm_teardown.classifier import (
    UNKNOWN,
    classify_text,
    is_negated,
    label,
    split_clauses,
)


def test_usage_based_pricing():
    c = classify_text("A", "Usage-based pricing: pay as you go, per API call.")
    assert c.pricing_model == "usage_based"
    assert c.pricing_evidence


def test_tiered_saas_pricing():
    c = classify_text("A", "Plans start at $29/mo. Compare plans: Starter plan, Pro plan, Enterprise plan.")
    assert c.pricing_model == "tiered_saas"


def test_seat_based_pricing():
    c = classify_text("A", "Simple per-seat pricing at $40/user.")
    assert c.pricing_model == "seat_based"


def test_custom_quote_pricing():
    c = classify_text("A", "Custom pricing for every deployment. Contact sales to get pricing.")
    assert c.pricing_model == "custom_quote"


def test_self_serve_motion():
    c = classify_text("A", "Sign up free, no credit card required. Start building today.")
    assert c.gtm_motion == "self_serve"


def test_sales_led_motion():
    c = classify_text("A", "Book a demo. Our dedicated implementation team handles rollout.")
    assert c.gtm_motion == "sales_led"


def test_hybrid_motion_needs_both_sides():
    c = classify_text("A", "Start a free trial today, or talk to sales for enterprise rollouts.")
    assert c.gtm_motion == "hybrid"


def test_themes_are_ranked_by_evidence_count():
    copy = ("SOC 2 and HIPAA compliant with audit logs and encryption. "
            "Integrates with Slack. Fast setup.")
    c = classify_text("A", copy)
    assert c.themes[0] == "security_compliance"
    assert "integration_ecosystem" in c.themes
    assert c.theme_counts()["security_compliance"] >= 3


def test_no_signal_gives_unknowns_and_no_confidence():
    c = classify_text("A", "Welcome to our website. We make software for people.")
    assert c.pricing_model == UNKNOWN
    assert c.gtm_motion == UNKNOWN
    assert c.themes == []
    assert not c.has_signal
    assert c.confidence == "none"


def test_evidence_snippets_are_clauses_from_the_copy():
    c = classify_text("A", "First sentence. Pay as you go with metered billing. Last sentence.")
    snippets = {e.snippet for e in c.pricing_evidence}
    assert "Pay as you go with metered billing" in snippets


def test_to_dict_is_json_friendly():
    d = classify_text("A", "Usage-based pricing.").to_dict()
    assert d["company"] == "A"
    assert d["pricing_model"] == "usage_based"
    assert isinstance(d["pricing_evidence"], list)
    assert d["has_signal"] is True


def test_split_clauses_boundaries():
    clauses = split_clauses("One; two: three -- four — five. Six? Seven! Eight\nNine | Ten")
    assert clauses == ["One", "two", "three", "four", "five", "Six", "Seven", "Eight", "Nine", "Ten"]


def test_split_clauses_keeps_decimal_points():
    assert split_clauses("Only $4.99 per month.") == ["Only $4.99 per month"]


def test_is_negated_window_is_local():
    clause = "we don't offer a self-serve plan"
    assert is_negated(clause, clause.index("self-serve"))
    clause2 = "there is honestly absolutely definitely no reason not to try the self-serve plan"
    # 'not' sits 3 words before 'the self-serve': inside the window -> negated (by design, conservative)
    assert is_negated(clause2, clause2.index("self-serve"))
    clause3 = "we are proud to offer a self-serve plan"
    assert not is_negated(clause3, clause3.index("self-serve"))


def test_labels_are_human_readable():
    assert label("usage_based") == "usage-based"
    assert label("made_up_key") == "made_up_key"
