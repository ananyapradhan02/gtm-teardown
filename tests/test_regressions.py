"""Named regression tests — one per bug found while dogfooding on real vendor copy.

Every build day of this tool found at least one pattern that "looked right until it was
run on real copy". Each is locked here with the day it was found, so the bug class can't
come back silently. See BUILD_LOG.md for the full history.
"""

from gtm_teardown.classifier import UNKNOWN, classify_text
from gtm_teardown.compare import compare
from gtm_teardown.reports import dominant, render_report
from gtm_teardown.store import SnapshotStore
from gtm_teardown.workflows import build_digest
from gtm_teardown.backends import HeuristicBackend


# --- Day 2 (2026-09-15) ------------------------------------------------------ #

def test_day2_bare_enterprise_keyword_is_not_tiered_pricing():
    """'Enterprise' alone was misclassifying custom-quote pricing as tiered SaaS."""
    c = classify_text("A", "Custom pricing for enterprise teams. Contact sales to get pricing.")
    assert c.pricing_model == "custom_quote"
    assert all(e.category != "tiered_saas" for e in c.pricing_evidence)


def test_day2_enterprise_plan_with_the_word_plan_is_still_tiered_evidence():
    c = classify_text("A", "Choose your plan: Starter plan, Team plan or Enterprise plan.")
    assert c.pricing_model == "tiered_saas"


# --- Day 3 (2026-09-16) ------------------------------------------------------ #

def test_day3_negated_self_serve_is_not_plg():
    """'no self-serve plans' matched the bare 'self-serve' PLG pattern."""
    c = classify_text("A", "There are no self-serve plans. Talk to our team to get started.")
    assert c.gtm_motion == "sales_led"
    assert any(e.category == "self_serve" for e in c.negated)


# --- Day 4 (2026-09-17) ------------------------------------------------------ #

def test_day4_save_two_digit_percent_matches_roi():
    """'save 40%' missed because the pattern used \\d instead of \\d+."""
    c = classify_text("A", "Teams save 40% on support costs with our agents.")
    assert "roi_cost_savings" in c.themes


# --- Day 6 (2026-09-19) ------------------------------------------------------ #

def test_day6a_negation_does_not_leak_across_sentence_boundary():
    """A fixed char window saw 'no ' from the previous sentence and negated the next clause."""
    c = classify_text("A", "Build agents with no code required. Usage-based pricing keeps it simple.")
    assert c.pricing_model == "usage_based"
    assert "ease_of_use" in c.themes


def test_day6b_sales_led_phrase_variants():
    """'talk to our sales team' and 'talking to sales' were not in the sales-led phrase list."""
    assert classify_text("A", "Talk to our sales team to get started.").gtm_motion == "sales_led"
    assert classify_text("B", "Every rollout begins with talking to sales.").gtm_motion == "sales_led"


# --- Day 7 (2026-09-20) ------------------------------------------------------ #

def test_day7a_sales_team_noun_phrase_without_action_verb():
    """'works with our sales team' had no action verb and matched nothing."""
    c = classify_text("A", "Every customer works with our sales team on a tailored rollout.")
    assert c.gtm_motion == "sales_led"


def test_day7b_tiered_plans_enumeration():
    """'Tiered plans: Starter, Explorer, Pro, Enterprise' required 'tiered pricing' or '<name> plan'."""
    c = classify_text("A", "Tiered plans: Starter, Explorer, Pro, Enterprise.")
    assert c.pricing_model == "tiered_saas"


def test_day7c_compare_wedge_checks_pricing_before_themes():
    """An identical (empty) theme diff masked a real pricing gap; order must be pricing→motion→themes."""
    a = classify_text("A", "Usage-based pricing, pay as you go. Book a demo.")
    b = classify_text("B", "Custom pricing: contact sales to get pricing. Book a demo.")
    cmp = compare(a, b)
    assert cmp.shared_themes == [] and cmp.only_a == [] and cmp.only_b == []
    assert cmp.wedge.startswith("Pricing wedge")


def test_day7c_compare_wedge_motion_before_themes():
    a = classify_text("A", "Usage-based pricing. Sign up free.")
    b = classify_text("B", "Usage-based pricing. Book a demo with our sales team.")
    assert compare(a, b).wedge.startswith("Motion wedge")


def test_day7d_report_never_claims_unknown_is_dominant():
    """'unknown' was being named the dominant pricing/motion class when it was the largest bucket."""
    cs = [classify_text("A", "Welcome to our website."), classify_text("B", "We build things."),
          classify_text("C", "Usage-based pricing, pay as you go.")]
    assert dominant(__import__("collections").Counter(c.pricing_model for c in cs)) == ("usage_based", 1)
    report = render_report(cs)
    assert "dominant pricing model is unknown" not in report.lower()
    assert "2 of 3 companies give no pricing model signal" in report


def test_day7d_report_wording_when_everything_is_unknown():
    cs = [classify_text("A", "Welcome."), classify_text("B", "Hello.")]
    report = render_report(cs)
    assert "None of the 2 companies gives a readable pricing model signal" in report
    assert "None of the 2 companies gives a readable GTM motion signal" in report


# --- Day 8 (2026-09-21) ------------------------------------------------------ #

def test_day8a_negation_does_not_leak_across_dash_or_semicolon_clauses():
    """'no self-serve plans -- every customer works with our sales team' let 'no' negate the sales-led match."""
    c = classify_text("A", "There are no self-serve plans -- every customer works with our sales team.")
    assert c.gtm_motion == "sales_led"
    c2 = classify_text("B", "No self-serve plans; talk to our sales team.")
    assert c2.gtm_motion == "sales_led"


def test_day8b_save_you_or_save_customers_percent():
    """'save you 30%' / 'save customers 40%' — verb and percentage were required to be adjacent."""
    assert "roi_cost_savings" in classify_text("A", "We save you 30% on tooling.").themes
    assert "roi_cost_savings" in classify_text("B", "Agents that save customers 40% per ticket.").themes


# --- Day 9 (2026-09-23) ------------------------------------------------------ #

def test_day9_digest_takes_raw_pairs_and_snapshots_them(examples_csv, store_path):
    """build_digest received pre-classified objects and crashed hashing a non-string in the snapshot step."""
    from gtm_teardown.sources import read_companies_csv
    pairs = read_companies_csv(str(examples_csv))
    d = build_digest(pairs, HeuristicBackend(), SnapshotStore(store_path), top_n=3)
    assert len(d.entries) == len(pairs)
    assert set(d.baselined) == {c for c, _ in pairs}
    assert all(SnapshotStore(store_path).latest(c) is not None for c, _ in pairs)


# --- Day 10 (2026-09-24) ----------------------------------------------------- #

def test_day10a_saving_and_saved_percent_inflections():
    """Only the bare verb 'save X%' matched; real copy says 'saving 40%' / 'saved 40%'."""
    assert "roi_cost_savings" in classify_text("A", "Customers report saving 40% on support costs.").themes
    assert "roi_cost_savings" in classify_text("B", "One team saved 25% in the first quarter.").themes


def test_day10b_talk_to_our_sales_team_for_pricing_is_custom_quote():
    """Only 'talk to our sales for pricing' matched; the inserted 'team' broke it."""
    c = classify_text("A", "Talk to our sales team for pricing.")
    assert c.pricing_model == "custom_quote"


# --- Day 12 (2026-09-26) ----------------------------------------------------- #

def test_day12_up_and_running_in_minutes_is_not_motion_evidence():
    """Sales-led vendors say 'up and running in minutes' about post-sales onboarding too;
    counting it as self-serve evidence manufactured false 'hybrid' classifications."""
    c = classify_text("A", "Book a demo with our sales team. Once onboarded you're up and running in minutes.")
    assert c.gtm_motion == "sales_led"
    assert "ease_of_use" in c.themes
    assert all(e.category != "self_serve" for e in c.motion_evidence)


# --- Day 13 (2026-09-26, first run against real pricing pages) ---------------- #

def test_day13a_price_pattern_after_a_space_was_dead_code():
    """'\\b\\$' never matches between a space and '$', so '$185/mo' and '$40/user' matched nothing."""
    c = classify_text("Clay", "Launch (starting at $185/mo) - the best way to start.")
    assert c.pricing_model == "tiered_saas"
    assert any("$" in e.pattern for e in c.pricing_evidence)
    c2 = classify_text("A", "Simple pricing: $40/user.")
    assert c2.pricing_model == "seat_based"


def test_day13b_credits_and_pay_only_when_are_usage_signals():
    """Lindy/Clay/Fin phrase usage pricing as 'credits' and 'pay only when' — no 'usage-based' anywhere."""
    assert classify_text("Fin", "Pay only when Fin delivers value.").pricing_model == "usage_based"
    lindy = classify_text("Lindy", "Credits measure the work Lindy does. You only use them when Lindy is working.")
    assert any(e.category == "usage_based" for e in lindy.pricing_evidence)
    clay = classify_text("Clay", "Data Credits are used when you purchase data from Clay's marketplace.")
    assert clay.pricing_model == "usage_based"


def test_day13c_cost_reduction_nominalisations_and_verbs():
    """Only 'reduce/cut/lower ... costs' matched; real pages say 'reduction in costs',
    'Decrease costs per lead', 'Save costs', 'support costs go down'."""
    for copy in ("65% reduction in costs.", "Decrease costs per lead.", "Save costs.",
                 "As Fin handles more conversations, your support costs go down."):
        assert "roi_cost_savings" in classify_text("A", copy).themes, copy


def test_day13d_without_supervision_is_autonomy_not_a_negation():
    """'execute complex tasks without supervision to drive results autonomously' (11x):
    'without' was negating 'autonomously' five words later."""
    c = classify_text("11x", "Independent, proactive, and able to execute complex tasks without supervision to drive results autonomously.")
    assert "autonomy_agents" in c.themes
    assert not any(e.category == "autonomy_agents" for e in c.negated)
    # 'without' still negates the noun right after it.
    assert classify_text("B", "Deploy without a sales team.").gtm_motion == "unknown"


def test_day13e_one_clause_is_one_hit_per_theme():
    """A clause listing five integration names counted five times and out-ranked the
    theme the page actually leads with."""
    c = classify_text("A", "Works with Salesforce, HubSpot, Slack, Zendesk and Jira via API and SDK.")
    assert c.theme_counts()["integration_ecosystem"] == 1


def test_day13f_schedule_your_custom_demo_is_sales_led():
    assert classify_text("Ada", "Schedule your custom demo.").gtm_motion == "sales_led"


def test_day13g_csv_url_column_fetches_live_copy(tmp_path):
    """A companies CSV can carry a url column instead of (or as well as) copy."""
    from gtm_teardown.sources import read_companies_csv
    p = tmp_path / "c.csv"
    p.write_text("company,url,copy\nA,https://a.example/pricing,\nB,https://b.example/,Pasted copy wins\nC,,\n")
    fetched = {"https://a.example/pricing": "Usage-based pricing."}
    rows = read_companies_csv(str(p), fetcher=lambda u: fetched[u])
    assert rows == [("A", "Usage-based pricing."), ("B", "Pasted copy wins")]


def test_day13g_csv_url_fetch_failure_skips_row_not_batch(tmp_path, capsys):
    from gtm_teardown.sources import read_companies_csv
    p = tmp_path / "c.csv"
    p.write_text("company,url\nA,https://dead.example/\nB,https://ok.example/\n")

    def fetcher(u):
        if "dead" in u:
            raise OSError("connection refused")
        return "Book a demo."
    assert read_companies_csv(str(p), fetcher=fetcher) == [("B", "Book a demo.")]
    assert "could not fetch" in capsys.readouterr().err


def test_day13h_report_does_not_call_a_tie_a_leader():
    """Three pricing models at 1 each were reported as 'usage-based leads (1 of 6)'."""
    cs = [classify_text("A", "Usage-based pricing."), classify_text("B", "Per-seat pricing."),
          classify_text("C", "Tiered plans: Starter, Pro."), classify_text("D", "Hello."), classify_text("E", "Hi."),
          classify_text("F", "Hey.")]
    report = render_report(cs)
    assert "no single pricing model leads" in report
    assert "usage-based leads" not in report


def test_day13i_essay_seed_does_not_say_most_on_a_tie():
    from gtm_teardown.reports import essay_seed
    cs = [classify_text("A", "Usage-based pricing. Book a demo."), classify_text("B", "Per-seat pricing. Book a demo."),
          classify_text("C", "Tiered plans: Starter, Pro. Book a demo."), classify_text("D", "Book a demo."),
          classify_text("E", "Book a demo."), classify_text("F", "Book a demo.")]
    seed = essay_seed(cs)
    assert "Most of this set sells" not in seed
    assert "publish no readable pricing model" in seed or "split evenly" in seed
    assert "most of this set runs sales-led" in seed
