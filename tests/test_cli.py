"""End-to-end CLI tests: every subcommand, run as a subprocess against examples/companies.csv."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = str(ROOT / "examples" / "companies.csv")


def run(*args, expect=0):
    proc = subprocess.run([sys.executable, "-m", "gtm_teardown", *args], cwd=ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == expect, f"exit {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    return proc.stdout


def test_version():
    assert run("--version").startswith("gtm-teardown ")


def test_run_from_csv_and_text_and_file(tmp_path):
    assert "# GTM teardown: Northwind Agents" in run("run", "--company", "Northwind Agents", "--csv", CSV)
    out = json.loads(run("run", "--company", "X", "--text", "Usage-based pricing.", "--format", "json"))
    assert out["pricing_model"] == "usage_based"
    f = tmp_path / "copy.txt"
    f.write_text("Book a demo with our sales team.")
    assert "sales-led" in run("run", "--company", "Y", "--file", str(f), "--format", "table")


def test_run_unknown_company_is_a_clean_error():
    proc = subprocess.run([sys.executable, "-m", "gtm_teardown", "run", "--company", "Nope", "--csv", CSV],
                          cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 1 and "not in CSV" in proc.stderr


def test_batch_writes_one_report_per_company(tmp_path):
    out = tmp_path / "reports"
    run("batch", "--csv", CSV, "--out", str(out))
    assert sorted(p.name for p in out.iterdir()) == [
        "cobalt-reach.md", "harbor-copilot.md", "lumen-ops.md", "meridian-ai.md", "northwind-agents.md", "summary.json"]
    assert len(json.loads((out / "summary.json").read_text())) == 5


def test_compare():
    out = run("compare", "--csv", CSV, "Northwind Agents", "Lumen Ops")
    assert "# Northwind Agents vs Lumen Ops" in out and "Pricing wedge" in out


def test_rank_table_csv_md(tmp_path):
    assert "Northwind Agents" in run("rank", "--csv", CSV).splitlines()[2]
    assert run("rank", "--csv", CSV, "--format", "csv").splitlines()[0].startswith("rank,company,score")
    assert run("rank", "--csv", CSV, "--format", "md", "--top", "2").count("| ") > 0


def test_report_landscape_and_rank_mode(tmp_path):
    assert "## Takeaway (essay seed)" in run("report", "--csv", CSV)
    out_file = tmp_path / "rank.md"
    run("report", "--csv", CSV, "--mode", "rank", "--out", str(out_file))
    assert out_file.read_text().startswith("# ICP ranking")


def test_essay():
    out = run("essay", "--csv", CSV, "--title", "Test title")
    assert out.startswith("# Test title") and "## The thesis" in out


def test_snapshot_diff_roundtrip(tmp_path):
    store = str(tmp_path / "s.json")
    assert "snapshot recorded" in run("snapshot", "--company", "Lumen Ops", "--csv", CSV, "--store", store)
    assert "no change" in run("snapshot", "--company", "Lumen Ops", "--csv", CSV, "--store", store)
    assert "nothing to compare" in run("diff", "--company", "Lumen Ops", "--store", store)
    run("snapshot", "--company", "Lumen Ops", "--text", "Custom pricing; talk to our sales team for pricing.", "--store", store)
    assert "[HIGH]" in run("diff", "--company", "Lumen Ops", "--store", store)


def test_outreach_exit_codes():
    assert "hook: theme" in run("outreach", "--company", "Northwind Agents", "--csv", CSV)
    assert "Refusing to invent a hook" in run("outreach", "--company", "Z", "--text", "Welcome.", expect=2)


def test_digest_brief_watch(tmp_path):
    store = str(tmp_path / "s.json")
    digest = run("digest", "--csv", CSV, "--store", store, "--top", "2")
    assert "## Openers for the top 2" in digest and "Baselined 5 new companies" in digest
    brief = run("brief", "--company", "Harbor Copilot", "--csv", CSV, "--store", store)
    assert "# Call prep: Harbor Copilot" in brief and "no change" in brief
    assert "Nothing crossed the medium bar" in run("watch", "--csv", CSV, "--store", store)
    moved = tmp_path / "moved.csv"
    moved.write_text(Path(CSV).read_text().replace("Sign up free, no credit card required, and be up and running in minutes.",
                                                   "Custom pricing; talk to our sales team for pricing. Book a demo."))
    out = run("watch", "--csv", str(moved), "--store", store)
    assert "1 company moved" in out and "Lumen Ops [HIGH]" in out


def test_llm_flag_falls_back_cleanly():
    proc = subprocess.run([sys.executable, "-m", "gtm_teardown", "run", "--company", "X", "--text", "Usage-based pricing.",
                           "--llm", "--format", "json"], cwd=ROOT, capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)})
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["backend"].startswith("heuristic (llm fallback")
