from gtm_teardown.backends import HeuristicBackend, LLMBackend, get_backend
from gtm_teardown.classifier import classify_text
from gtm_teardown.outreach import draft_opener, render_opener
from gtm_teardown.sources import html_to_text, read_companies_csv
from gtm_teardown.store import SnapshotStore
from gtm_teardown.workflows import build_brief, build_digest, render_brief, render_digest


# --- outreach ---------------------------------------------------------------- #

def test_opener_prefers_theme_then_motion_then_pricing():
    theme = draft_opener(classify_text("A", "SOC 2 compliant. Book a demo. Usage-based pricing."))
    assert theme and theme.hook_type == "theme" and theme.hook_key == "security_compliance"
    motion = draft_opener(classify_text("B", "Book a demo. Usage-based pricing."))
    assert motion and motion.hook_type == "motion"
    pricing = draft_opener(classify_text("C", "Usage-based pricing."))
    assert pricing and pricing.hook_type == "pricing"


def test_opener_refuses_to_invent_a_hook():
    op = draft_opener(classify_text("Blank", "Welcome to our website."))
    assert op is None
    assert "Refusing to invent a hook" in render_opener(op, "Blank")


def test_opener_appends_sender_context_and_evidence():
    op = draft_opener(classify_text("A", "Customers save 40% on costs."), sender_context="I write about this.")
    assert op.line.endswith("I write about this.")
    assert op.evidence == "Customers save 40% on costs"
    assert "Grounded in their copy" in render_opener(op, "A")


# --- digest ------------------------------------------------------------------ #

def test_digest_skips_no_signal_company_instead_of_faking(store_path, tmp_path):
    pairs = [("Real", "Usage-based pricing. Book a demo. SOC 2 compliant."), ("Blank", "Welcome.")]
    d = build_digest(pairs, HeuristicBackend(), SnapshotStore(store_path), top_n=2)
    blank = next(e for e in d.entries if e.scored.company == "Blank")
    assert blank.opener is None and "skipped" in blank.skipped_reason
    out = render_digest(d)
    assert "_Skipped:" in out and "### Real" in out


def test_digest_reports_drift_on_second_run(store_path, examples_csv):
    pairs = read_companies_csv(str(examples_csv))
    store = SnapshotStore(store_path)
    build_digest(pairs, HeuristicBackend(), store, top_n=1)
    moved = [(c, t if c != "Lumen Ops" else "Custom pricing; talk to our sales team for pricing. Book a demo.") for c, t in pairs]
    d = build_digest(moved, HeuristicBackend(), store, top_n=1)
    out = render_digest(d)
    assert "Lumen Ops [HIGH]" in out
    assert d.baselined == []


# --- brief ------------------------------------------------------------------- #

def test_brief_has_score_drift_and_opener(store_path):
    copy = "Autonomous AI agents resolve tickets end-to-end. Talk to our sales team for pricing. SOC 2."
    b = build_brief("Acme", copy, HeuristicBackend(), SnapshotStore(store_path))
    out = render_brief(b)
    assert "# Call prep: Acme" in out
    assert f"**{b.scored.score} / {b.max_score}**" in out
    assert "baseline recorded" in out
    assert "## Opening line" in out and "## Their words to quote back" in out


# --- backends ---------------------------------------------------------------- #

def test_llm_backend_falls_back_without_key_and_says_so(capsys):
    backend = get_backend(use_llm=True)
    assert isinstance(backend, LLMBackend)
    c = backend.classify("A", "Usage-based pricing.")
    assert c.pricing_model == "usage_based"
    assert c.backend.startswith("heuristic (llm fallback")
    assert "LLM backend unavailable" in capsys.readouterr().err


def test_llm_validate_rejects_unknown_categories():
    c = LLMBackend._validate("A", "copy", {"pricing_model": "made_up", "gtm_motion": "sales_led",
                                            "themes": ["autonomy_agents", "nope"], "evidence": {"sales_led": "Book a demo"}})
    assert c.pricing_model == "unknown" and c.gtm_motion == "sales_led" and c.themes == ["autonomy_agents"]
    assert c.motion_evidence[0].snippet == "Book a demo" and c.backend == "llm"


# --- sources ----------------------------------------------------------------- #

def test_csv_reader_accepts_text_column_and_skips_empty(tmp_path, capsys):
    p = tmp_path / "c.csv"
    p.write_text("Company,Text\nA,hello\nB,\n,orphan\n")
    assert read_companies_csv(str(p)) == [("A", "hello")]
    assert "skipping B" in capsys.readouterr().err


def test_csv_reader_requires_columns(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("name,blurb\nA,hello\n")
    try:
        read_companies_csv(str(p))
    except ValueError as exc:
        assert "company" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_html_to_text_strips_scripts_and_tags():
    html = "<html><head><style>x{}</style><script>var a=1;</script></head><body><h1>Pay as you go</h1><p>Book a &amp; demo</p></body></html>"
    text = html_to_text(html)
    assert "var a" not in text and "Pay as you go" in text and "Book a & demo" in text
