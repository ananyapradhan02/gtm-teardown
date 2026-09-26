"""ICP-fit scoring against a weighted rubric.

A rubric is a JSON object with three weight maps::

    {
      "pricing_model": {"custom_quote": 3, "usage_based": 3, "seat_based": 1, "tiered_saas": 2},
      "gtm_motion":    {"sales_led": 3, "hybrid": 3, "self_serve": 1},
      "themes":        {"autonomy_agents": 3, "roi_cost_savings": 2, ...},
      "theme_cap":     3            # optional: only the top N themes count
    }

Missing keys score 0, so a rubric can be as small as one line. Swap it with ``--rubric``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .classifier import Classification, label

DEFAULT_RUBRIC: dict = {
    "name": "agentic-AI GTM outbound fit (default)",
    "pricing_model": {"custom_quote": 3, "usage_based": 3, "seat_based": 1, "tiered_saas": 2},
    "gtm_motion": {"sales_led": 3, "hybrid": 3, "self_serve": 1},
    "themes": {
        "autonomy_agents": 3,
        "roi_cost_savings": 2,
        "security_compliance": 2,
        "scale_enterprise": 2,
        "integration_ecosystem": 1,
        "accuracy_reliability": 1,
        "human_in_the_loop": 1,
        "speed_time_to_value": 1,
        "ease_of_use": 0,
    },
    "theme_cap": 3,
}


def load_rubric(path: str | None) -> dict:
    if not path:
        return DEFAULT_RUBRIC
    with open(path, encoding="utf-8") as fh:
        rubric = json.load(fh)
    for key in ("pricing_model", "gtm_motion", "themes"):
        rubric.setdefault(key, {})
    rubric.setdefault("theme_cap", 3)
    rubric.setdefault("name", path)
    return rubric


@dataclass
class Scored:
    classification: Classification
    score: int
    breakdown: Dict[str, int]

    @property
    def company(self) -> str:
        return self.classification.company


def max_score(rubric: dict) -> int:
    top = lambda m: max(m.values()) if m else 0  # noqa: E731
    themes = sorted(rubric["themes"].values(), reverse=True)[: rubric.get("theme_cap", 3)]
    return top(rubric["pricing_model"]) + top(rubric["gtm_motion"]) + sum(v for v in themes if v > 0)


def score(c: Classification, rubric: dict | None = None) -> Scored:
    rubric = rubric or DEFAULT_RUBRIC
    breakdown = {
        "pricing": int(rubric["pricing_model"].get(c.pricing_model, 0)),
        "motion": int(rubric["gtm_motion"].get(c.gtm_motion, 0)),
    }
    cap = rubric.get("theme_cap", 3)
    theme_pts = [int(rubric["themes"].get(t, 0)) for t in c.themes[:cap]]
    breakdown["themes"] = sum(theme_pts)
    return Scored(classification=c, score=sum(breakdown.values()), breakdown=breakdown)


def rank(classifications: Sequence[Classification], rubric: dict | None = None) -> List[Scored]:
    rubric = rubric or DEFAULT_RUBRIC
    scored = [score(c, rubric) for c in classifications]
    # Highest score first; ties broken by confidence then name so output is stable.
    conf_order = {"high": 3, "medium": 2, "low": 1, "none": 0}
    scored.sort(key=lambda s: (-s.score, -conf_order[s.classification.confidence], s.company.lower()))
    return scored


def rank_rows(scored: Sequence[Scored]) -> Tuple[List[str], List[List[str]]]:
    headers = ["rank", "company", "score", "pricing", "motion", "top_theme", "confidence"]
    rows = []
    for i, s in enumerate(scored, 1):
        c = s.classification
        rows.append([str(i), c.company, str(s.score), label(c.pricing_model), label(c.gtm_motion),
                     label(c.top_theme() or "unknown"), c.confidence])
    return headers, rows
