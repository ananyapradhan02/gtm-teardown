"""Command-line interface: 12 subcommands over one classifier.

    run · batch · compare · rank · report · essay · snapshot · diff · outreach · digest · brief · watch
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .backends import get_backend
from .classifier import Classification
from .compare import compare, render_comparison
from .outreach import draft_opener, render_opener
from .rank import load_rubric, rank, rank_rows
from .render import render
from .reports import render_essay, render_rank_report, render_report
from .sources import find_company, read_companies_csv, read_copy, slugify, text_table
from .store import DEFAULT_STORE, SnapshotStore, watch
from .workflows import build_brief, build_digest, render_brief, render_digest


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _add_copy_args(p: argparse.ArgumentParser, csv_ok: bool = False) -> None:
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="copy as a literal string")
    g.add_argument("--file", help="path to a text/markdown/html file with the copy")
    g.add_argument("--url", help="fetch the page and strip HTML")
    if csv_ok:
        g.add_argument("--csv", help="companies CSV; pick the row by --company")


def _add_backend_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--llm", action="store_true",
                   help="use the Claude backend (needs ANTHROPIC_API_KEY); falls back to heuristic on any failure")
    p.add_argument("--model", default=None, help="model id for --llm (default: $GTM_TEARDOWN_MODEL or claude-sonnet-5)")


def _backend(args):
    kwargs = {"use_llm": args.llm}
    if getattr(args, "model", None):
        kwargs["model"] = args.model
    return get_backend(**kwargs)


def _copy_for(args) -> str:
    if getattr(args, "csv", None):
        _, copy = find_company(read_companies_csv(args.csv), args.company)
        return copy
    return read_copy(text=args.text, file=args.file, url=args.url)


def _out(text: str, path: Optional[str]) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _classify_csv(args) -> List[Classification]:
    backend = _backend(args)
    return [backend.classify(company, copy) for company, copy in read_companies_csv(args.csv)]


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def cmd_run(args) -> int:
    c = _backend(args).classify(args.company, _copy_for(args))
    _out(render(c, args.format), args.out)
    return 0


def cmd_batch(args) -> int:
    backend = _backend(args)
    rows = read_companies_csv(args.csv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for company, copy in rows:
        c = backend.classify(company, copy)
        ext = "json" if args.format == "json" else "md"
        path = out_dir / f"{slugify(company)}.{ext}"
        path.write_text(render(c, args.format), encoding="utf-8")
        summary.append({"company": c.company, "pricing_model": c.pricing_model, "gtm_motion": c.gtm_motion,
                        "themes": c.themes, "confidence": c.confidence, "report": str(path)})
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{len(summary)} reports written to {out_dir}/ (+ summary.json)")
    return 0


def cmd_compare(args) -> int:
    backend = _backend(args)
    rows = read_companies_csv(args.csv)
    a = backend.classify(*find_company(rows, args.a))
    b = backend.classify(*find_company(rows, args.b))
    _out(render_comparison(compare(a, b)), args.out)
    return 0


def cmd_rank(args) -> int:
    rubric = load_rubric(args.rubric)
    scored = rank(_classify_csv(args), rubric)
    if args.top:
        scored = scored[: args.top]
    headers, rows = rank_rows(scored)
    if args.format == "csv":
        w = csv.writer(sys.stdout)
        w.writerow(headers)
        w.writerows(rows)
    elif args.format == "md":
        _out(render_rank_report(scored, rubric.get("name", "custom")), args.out)
    else:
        print(text_table(headers, rows))
        print(f"\nrubric: {rubric.get('name', 'custom')}")
    return 0


def cmd_report(args) -> int:
    cs = _classify_csv(args)
    if args.mode == "rank":
        rubric = load_rubric(args.rubric)
        _out(render_rank_report(rank(cs, rubric), rubric.get("name", "custom"), title=args.title or "ICP ranking"), args.out)
    else:
        _out(render_report(cs, title=args.title or "GTM landscape"), args.out)
    return 0


def cmd_essay(args) -> int:
    _out(render_essay(_classify_csv(args), title=args.title, author=args.author), args.out)
    return 0


def cmd_snapshot(args) -> int:
    copy = _copy_for(args)
    c = _backend(args).classify(args.company, copy)
    store = SnapshotStore(args.store)
    snap, created = store.snapshot(c, copy)
    if created:
        print(f"snapshot recorded for {c.company} at {snap.taken_at} (sha {snap.sha}, {len(store.history(c.company))} total)")
    else:
        print(f"no change: copy identical to last snapshot of {c.company} ({snap.taken_at}, sha {snap.sha})")
    return 0


def cmd_diff(args) -> int:
    d = SnapshotStore(args.store).diff(args.company)
    print(d.describe())
    return 0


def cmd_outreach(args) -> int:
    c = _backend(args).classify(args.company, _copy_for(args))
    op = draft_opener(c, sender_context=args.context)
    _out(render_opener(op, c.company), args.out)
    return 0 if op else 2


def cmd_digest(args) -> int:
    d = build_digest(read_companies_csv(args.csv), _backend(args), SnapshotStore(args.store),
                     load_rubric(args.rubric), top_n=args.top)
    _out(render_digest(d, title=args.title or "Weekly GTM digest"), args.out)
    return 0


def cmd_brief(args) -> int:
    b = build_brief(args.company, _copy_for(args), _backend(args), SnapshotStore(args.store), load_rubric(args.rubric))
    _out(render_brief(b), args.out)
    return 0


def cmd_watch(args) -> int:
    backend = _backend(args)
    items = [(backend.classify(company, copy), copy) for company, copy in read_companies_csv(args.csv)]
    significant, quiet = watch(SnapshotStore(args.store), items, min_level=args.min_level)
    baselined = [d.company for d in quiet if d.baseline]
    lines = []
    if significant:
        n = len(significant)
        lines.append(f"{n} {'company' if n == 1 else 'companies'} moved (≥ {args.min_level}):")
        lines += [f"  - {d.describe()}" for d in significant]
    else:
        lines.append(f"Nothing crossed the {args.min_level} bar across {len(items)} companies.")
    if baselined:
        lines.append(f"Baselined {len(baselined)} new: {', '.join(baselined)}")
    unchanged = len(quiet) - len(baselined)
    if unchanged:
        lines.append(f"{unchanged} unchanged or cosmetic.")
    _out("\n".join(lines), args.out)
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gtm-teardown",
                                description="Classify how agentic-AI companies go to market from their public copy.")
    p.add_argument("--version", action="version", version=f"gtm-teardown {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("run", help="teardown of one company")
    s.add_argument("--company", required=True)
    _add_copy_args(s, csv_ok=True)
    _add_backend_args(s)
    s.add_argument("--format", choices=["md", "json", "table"], default="md")
    s.add_argument("--out")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("batch", help="CSV in, one report per company out")
    s.add_argument("--csv", required=True)
    s.add_argument("--out", default="reports")
    s.add_argument("--format", choices=["md", "json"], default="md")
    _add_backend_args(s)
    s.set_defaults(func=cmd_batch)

    s = sub.add_parser("compare", help="head-to-head positioning diff of two companies in a CSV")
    s.add_argument("--csv", required=True)
    s.add_argument("a")
    s.add_argument("b")
    _add_backend_args(s)
    s.add_argument("--out")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("rank", help="score a CSV of companies for ICP fit")
    s.add_argument("--csv", required=True)
    s.add_argument("--rubric", help="JSON rubric (default: built-in agentic-AI outbound rubric)")
    s.add_argument("--top", type=int, default=0)
    s.add_argument("--format", choices=["table", "csv", "md"], default="table")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_rank)

    s = sub.add_parser("report", help="Markdown landscape write-up from a CSV")
    s.add_argument("--csv", required=True)
    s.add_argument("--mode", choices=["landscape", "rank"], default="landscape")
    s.add_argument("--rubric")
    s.add_argument("--title")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("essay", help="full essay draft (with [spans] for your own argument) from a CSV")
    s.add_argument("--csv", required=True)
    s.add_argument("--title")
    s.add_argument("--author", default="Ananya Pradhan")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_essay)

    s = sub.add_parser("snapshot", help="record a dated, hashed snapshot of a company's copy")
    s.add_argument("--company", required=True)
    _add_copy_args(s, csv_ok=True)
    s.add_argument("--store", default=DEFAULT_STORE)
    _add_backend_args(s)
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("diff", help="positioning drift between the two most recent snapshots")
    s.add_argument("--company", required=True)
    s.add_argument("--store", default=DEFAULT_STORE)
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("outreach", help="draft a personalised cold-outreach opener from a teardown")
    s.add_argument("--company", required=True)
    _add_copy_args(s, csv_ok=True)
    s.add_argument("--context", help="one sentence about you to append (optional)")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_outreach)

    s = sub.add_parser("digest", help="weekly triage: rank + drift + openers for the top N")
    s.add_argument("--csv", required=True)
    s.add_argument("--store", default=DEFAULT_STORE)
    s.add_argument("--rubric")
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--title")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_digest)

    s = sub.add_parser("brief", help="one-page call prep for a single account")
    s.add_argument("--company", required=True)
    _add_copy_args(s, csv_ok=True)
    s.add_argument("--store", default=DEFAULT_STORE)
    s.add_argument("--rubric")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_brief)

    s = sub.add_parser("watch", help="scan a watchlist CSV and report only significant positioning drift")
    s.add_argument("--csv", required=True)
    s.add_argument("--store", default=DEFAULT_STORE)
    s.add_argument("--min-level", choices=["medium", "high"], default="medium")
    s.add_argument("--out")
    _add_backend_args(s)
    s.set_defaults(func=cmd_watch)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        print(f"gtm-teardown: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
