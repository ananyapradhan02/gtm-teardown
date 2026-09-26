"""Recurring-use workflows that fuse the primitives.

* ``build_digest`` – Monday-morning triage: rank a watchlist by ICP fit, report drift per
  company (silently baselining first-ever snapshots), and draft openers for the top N.
  It takes raw ``(company, copy)`` pairs and classifies internally (Day 9 regression:
  passing pre-classified objects broke the snapshot step, which needs the raw copy).
* ``build_brief`` – one-page call prep for a single account: ICP score, drift versus the
  last snapshot, and the opening line, in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Sequence, Tuple

from .classifier import UNKNOWN, Classification, label
from .outreach import Opener, draft_opener, render_opener
from .rank import DEFAULT_RUBRIC, Scored, max_score, rank, rank_rows, score
from .sources import md_table
from .store import Drift, SnapshotStore

Backend = object  # anything with .classify(company, text) -> Classification


# --------------------------------------------------------------------------- #
# digest
# --------------------------------------------------------------------------- #

@dataclass
class DigestEntry:
    scored: Scored
    drift: Drift
    opener: Optional[Opener]
    skipped_reason: Optional[str] = None


@dataclass
class Digest:
    entries: List[DigestEntry]
    rubric_name: str
    top_n: int
    max_score: int
    baselined: List[str] = field(default_factory=list)


def build_digest(pairs: Sequence[Tuple[str, str]], backend, store: SnapshotStore,
                 rubric: dict | None = None, top_n: int = 5) -> Digest:
    rubric = rubric or DEFAULT_RUBRIC
    classified: List[Tuple[Classification, str]] = [(backend.classify(company, copy), copy) for company, copy in pairs]
    by_name = {c.company: text for c, text in classified}
    ranked = rank([c for c, _ in classified], rubric)

    entries: List[DigestEntry] = []
    baselined: List[str] = []
    for i, s in enumerate(ranked):
        c = s.classification
        drift = store.track(c, by_name[c.company])
        if drift.baseline:
            baselined.append(c.company)
        opener, why = None, None
        if i < top_n:
            opener = draft_opener(c)
            if opener is None:
                why = "no usable signal in copy — opener skipped rather than faked"
        entries.append(DigestEntry(scored=s, drift=drift, opener=opener, skipped_reason=why))
    return Digest(entries=entries, rubric_name=rubric.get("name", "custom"), top_n=top_n,
                  max_score=max_score(rubric), baselined=baselined)


def render_digest(d: Digest, title: str = "Weekly GTM digest") -> str:
    headers, rows = rank_rows([e.scored for e in d.entries])
    lines = [f"# {title}", "", f"*{date.today().isoformat()} · {len(d.entries)} companies · rubric: {d.rubric_name} (max {d.max_score})*", "",
             "## Priority (ICP fit)", "", md_table(headers, rows), ""]

    drifted = [e for e in d.entries if not e.drift.baseline and e.drift.has_drift]
    lines += ["## Positioning drift since last run", ""]
    if drifted:
        for e in sorted(drifted, key=lambda e: e.drift.level != "high"):
            lines.append(f"- {e.drift.describe()}")
    else:
        lines.append("- No positioning drift detected." + (f" Baselined {len(d.baselined)} new companies: {', '.join(d.baselined)}." if d.baselined else ""))
    if drifted and d.baselined:
        lines.append(f"- Baselined {len(d.baselined)} new companies: {', '.join(d.baselined)}.")
    lines.append("")

    lines += [f"## Openers for the top {d.top_n}", ""]
    for e in d.entries[: d.top_n]:
        c = e.scored.classification
        if e.opener:
            lines += [f"### {c.company} (score {e.scored.score}/{d.max_score})", "", e.opener.line, ""]
            if e.opener.evidence:
                lines += [f'_Grounded in: "{e.opener.evidence}"_', ""]
        else:
            lines += [f"### {c.company} (score {e.scored.score}/{d.max_score})", "", f"_Skipped: {e.skipped_reason}._", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# brief
# --------------------------------------------------------------------------- #

@dataclass
class Brief:
    classification: Classification
    scored: Scored
    drift: Drift
    opener: Optional[Opener]
    max_score: int
    rubric_name: str


def build_brief(company: str, copy: str, backend, store: SnapshotStore, rubric: dict | None = None) -> Brief:
    rubric = rubric or DEFAULT_RUBRIC
    c = backend.classify(company, copy)
    return Brief(classification=c, scored=score(c, rubric), drift=store.track(c, copy),
                 opener=draft_opener(c), max_score=max_score(rubric), rubric_name=rubric.get("name", "custom"))


def render_brief(b: Brief) -> str:
    c = b.classification
    themes = ", ".join(label(t) for t in c.themes) or "none detected"
    lines = [
        f"# Call prep: {c.company}",
        "",
        f"*{date.today().isoformat()} · gtm-teardown brief*",
        "",
        "## How they go to market",
        "",
        f"- **Pricing:** {label(c.pricing_model)}",
        f"- **Motion:** {label(c.gtm_motion)}",
        f"- **Themes:** {themes}",
        f"- **Confidence:** {c.confidence}",
        "",
        "## ICP fit",
        "",
        f"**{b.scored.score} / {b.max_score}** on rubric *{b.rubric_name}* "
        f"(pricing {b.scored.breakdown['pricing']}, motion {b.scored.breakdown['motion']}, themes {b.scored.breakdown['themes']})",
        "",
        "## What changed",
        "",
        f"- {b.drift.describe()}",
        "",
        "## Opening line",
        "",
        render_opener(b.opener, c.company),
        "",
    ]
    if c.evidence_for(c.top_theme() or UNKNOWN):
        lines += ["## Their words to quote back", ""]
        seen = set()
        for ev in (c.theme_evidence + c.motion_evidence + c.pricing_evidence):
            if ev.snippet in seen:
                continue
            seen.add(ev.snippet)
            lines.append(f'- "{ev.snippet}"')
            if len(seen) >= 4:
                break
        lines.append("")
    return "\n".join(lines)
