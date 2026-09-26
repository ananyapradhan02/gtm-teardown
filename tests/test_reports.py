from gtm_teardown.classifier import classify_text
from gtm_teardown.compare import compare, render_comparison
from gtm_teardown.rank import DEFAULT_RUBRIC, load_rubric, max_score, rank, score
from gtm_teardown.render import render
from gtm_teardown.reports import essay_seed, pick_vignettes, render_essay, render_rank_report, render_report
from gtm_teardown.sources import read_companies_csv


def _examples(path):
    return [classify_text(c, t) for c, t in read_companies_csv(str(path))]


def test_render_formats(examples_csv):
    c = _examples(examples_csv)[0]
    assert render(c, "md").startswith("# GTM teardown: ")
    assert '"company": "Northwind Agents"' in render(c, "json")
    assert "pricing_model" in render(c, "table")


def test_report_has_every_section_and_seed(examples_csv):
    out = render_report(_examples(examples_csv))
    for heading in ("## Pricing models", "## GTM motions", "## Messaging themes", "## Company table", "## Takeaway (essay seed)"):
        assert heading in out
    assert "unknown" not in out.split("## Takeaway")[1].lower()


def test_essay_seed_names_uncontested_theme():
    cs = [classify_text("A", "Usage-based pricing. SOC 2 compliant. Book a demo."),
          classify_text("B", "Usage-based pricing. GDPR compliant. Book a demo.")]
    seed = essay_seed(cs)
    assert "uncontested ground" in seed
    assert "security & compliance" not in seed.split("uncontested ground")[1]


def test_essay_structure_and_vignettes(examples_csv):
    cs = _examples(examples_csv)
    out = render_essay(cs, author="Test Author")
    for heading in ("## Hook", "## The landscape", "## Three companies, read closely", "## The thesis", "## Sign-off"):
        assert heading in out
    assert out.count("[") >= 5, "bracketed spans mark where the author's argument goes"
    assert "— Test Author" in out
    assert 2 <= len(pick_vignettes(cs)) <= 3


def test_essay_with_no_signal_batch_does_not_crash():
    out = render_essay([classify_text("A", "Hello."), classify_text("B", "World.")])
    assert "No company in this batch had enough signal" in out


def test_rank_orders_by_rubric_and_is_stable(examples_csv):
    ranked = rank(_examples(examples_csv))
    scores = [s.score for s in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0].company == "Northwind Agents"
    assert max(scores) <= max_score(DEFAULT_RUBRIC)


def test_custom_rubric_swaps_priorities(tmp_path, examples_csv):
    rubric_path = tmp_path / "plg.json"
    rubric_path.write_text('{"name":"plg","gtm_motion":{"self_serve":10},"themes":{"ease_of_use":5}}')
    rubric = load_rubric(str(rubric_path))
    ranked = rank(_examples(examples_csv), rubric)
    assert ranked[0].company == "Lumen Ops"
    assert score(ranked[0].classification, rubric).breakdown["pricing"] == 0


def test_rank_report_markdown(examples_csv):
    out = render_rank_report(rank(_examples(examples_csv)), "default")
    assert out.startswith("# ICP ranking") and "| rank |" in out


def test_compare_render_lists_shared_and_unique(examples_csv):
    cs = _examples(examples_csv)
    out = render_comparison(compare(cs[0], cs[1]))
    assert "## Positioning wedge" in out and "**Shared:**" in out


def test_compare_no_wedge_when_identical():
    a = classify_text("A", "Usage-based pricing. Book a demo. SOC 2.")
    b = classify_text("B", "Usage-based pricing. Book a demo. SOC 2.")
    assert compare(a, b).wedge.startswith("No wedge identified")
