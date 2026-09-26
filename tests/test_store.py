from gtm_teardown.classifier import classify_text
from gtm_teardown.store import LEVELS, SnapshotStore, watch

PLG = "Sign up free, no credit card required. Plans start at $29/mo. Integrates with Slack."
SALES = "Custom pricing; talk to our sales team for pricing. Book a demo. SOC 2 compliant."
PLG_COSMETIC = "Sign up free, no credit card required! Plans start at $29/mo. Integrates with Slack today."


def test_snapshot_is_noop_on_identical_copy(store_path):
    store = SnapshotStore(store_path)
    c = classify_text("Acme", PLG)
    _, created1 = store.snapshot(c, PLG)
    _, created2 = store.snapshot(c, PLG)
    assert created1 and not created2
    assert len(store.history("Acme")) == 1


def test_diff_reports_high_drift_on_pricing_or_motion_change(store_path):
    store = SnapshotStore(store_path)
    store.snapshot(classify_text("Acme", PLG), PLG, taken_at="2026-09-01T00:00:00+00:00")
    store.snapshot(classify_text("Acme", SALES), SALES, taken_at="2026-09-08T00:00:00+00:00")
    d = store.diff("Acme")
    assert d.level == "high" and d.pricing_changed and d.motion_changed
    assert "2026-09-01" in d.describe() and "→" in d.describe()


def test_diff_theme_only_change_is_medium(store_path):
    store = SnapshotStore(store_path)
    a = "Usage-based pricing. Book a demo. SOC 2 compliant."
    b = "Usage-based pricing. Book a demo. Integrates with Slack."
    store.snapshot(classify_text("Acme", a), a)
    store.snapshot(classify_text("Acme", b), b)
    d = store.diff("Acme")
    assert d.level == "medium"
    assert d.themes_added == ["integration_ecosystem"] and d.themes_removed == ["security_compliance"]


def test_cosmetic_edit_is_no_drift(store_path):
    store = SnapshotStore(store_path)
    store.snapshot(classify_text("Acme", PLG), PLG)
    store.snapshot(classify_text("Acme", PLG_COSMETIC), PLG_COSMETIC)
    d = store.diff("Acme")
    assert d.copy_changed and not d.has_drift and "cosmetic" in d.describe()


def test_diff_with_fewer_than_two_snapshots(store_path):
    store = SnapshotStore(store_path)
    assert "nothing to compare" in store.diff("Nobody").describe()


def test_store_persists_and_is_case_insensitive(store_path):
    SnapshotStore(store_path).snapshot(classify_text("Acme", PLG), PLG)
    reopened = SnapshotStore(store_path)
    assert reopened.latest("acme") is not None
    assert reopened.companies() == ["Acme"]


def test_track_baselines_silently_then_reports(store_path):
    store = SnapshotStore(store_path)
    first = store.track(classify_text("Acme", PLG), PLG)
    assert first.baseline and not first.has_drift
    second = store.track(classify_text("Acme", SALES), SALES)
    assert not second.baseline and second.level == "high"


def test_watch_filters_by_significance_and_sorts_urgent_first(store_path):
    store = SnapshotStore(store_path)
    for name, text in (("A", PLG), ("B", PLG), ("C", PLG)):
        store.snapshot(classify_text(name, text), text)
    items = [
        (classify_text("A", PLG_COSMETIC), PLG_COSMETIC),  # cosmetic → quiet
        (classify_text("B", "Sign up free, no credit card required. Plans start at $29/mo. SOC 2."), "Sign up free, no credit card required. Plans start at $29/mo. SOC 2."),  # theme swap → medium
        (classify_text("C", SALES), SALES),  # pricing+motion → high
        (classify_text("D", PLG), PLG),  # new → baseline, quiet
    ]
    significant, quiet = watch(store, items, min_level="medium")
    assert [d.company for d in significant] == ["C", "B"]
    assert {d.company for d in quiet} == {"A", "D"}
    assert LEVELS[significant[0].level] > LEVELS[significant[1].level]


def test_watch_high_bar_drops_medium(store_path):
    store = SnapshotStore(store_path)
    a = "Usage-based pricing. Book a demo. SOC 2 compliant."
    b = "Usage-based pricing. Book a demo. Integrates with Slack."
    store.snapshot(classify_text("A", a), a)
    significant, quiet = watch(store, [(classify_text("A", b), b)], min_level="high")
    assert significant == [] and quiet[0].level == "medium"
