"""Head-to-head competitive positioning diff between two companies.

The "positioning wedge" note is decided in a fixed order — pricing gap, then motion
gap, then theme gap (Day 7 regression: checking "identical themes" first let a real
pricing/motion gap get masked by a coincidentally empty theme diff).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .classifier import UNKNOWN, Classification, label
from .sources import md_table


@dataclass
class Comparison:
    a: Classification
    b: Classification
    shared_themes: List[str] = field(default_factory=list)
    only_a: List[str] = field(default_factory=list)
    only_b: List[str] = field(default_factory=list)
    wedge: str = ""


def positioning_wedge(a: Classification, b: Classification, shared, only_a, only_b) -> str:
    # 1. Pricing gap first.
    if a.pricing_model != b.pricing_model and UNKNOWN not in (a.pricing_model, b.pricing_model):
        return (f"Pricing wedge: {a.company} sells {label(a.pricing_model)} while {b.company} sells "
                f"{label(b.pricing_model)}. Buyers comparing the two will feel this before any feature.")
    # 2. Motion gap second.
    if a.gtm_motion != b.gtm_motion and UNKNOWN not in (a.gtm_motion, b.gtm_motion):
        return (f"Motion wedge: {a.company} is {label(a.gtm_motion)} and {b.company} is "
                f"{label(b.gtm_motion)}. Whoever wins the buyer's preferred buying path wins the deal.")
    # 3. Themes last.
    if only_a and only_b:
        return (f"Theme wedge: {a.company} owns {label(only_a[0])}; {b.company} owns {label(only_b[0])}. "
                f"Shared ground: {', '.join(label(t) for t in shared) or 'none'}.")
    if only_a:
        return f"Theme wedge: only {a.company} claims {label(only_a[0])} — {b.company} leaves it uncontested."
    if only_b:
        return f"Theme wedge: only {b.company} claims {label(only_b[0])} — {a.company} leaves it uncontested."
    if not a.has_signal or not b.has_signal:
        return "No wedge identified: at least one side has no usable signal in the copy provided."
    return "No wedge identified: same pricing model, same motion, same themes. Differentiation is not in the copy."


def compare(a: Classification, b: Classification) -> Comparison:
    sa, sb = set(a.themes), set(b.themes)
    shared = [t for t in a.themes if t in sb]
    only_a = [t for t in a.themes if t not in sb]
    only_b = [t for t in b.themes if t not in sa]
    return Comparison(a=a, b=b, shared_themes=shared, only_a=only_a, only_b=only_b,
                      wedge=positioning_wedge(a, b, shared, only_a, only_b))


def render_comparison(cmp: Comparison) -> str:
    a, b = cmp.a, cmp.b
    table = md_table(
        ["", a.company, b.company],
        [
            ("Pricing model", label(a.pricing_model), label(b.pricing_model)),
            ("GTM motion", label(a.gtm_motion), label(b.gtm_motion)),
            ("Top theme", label(a.top_theme() or UNKNOWN), label(b.top_theme() or UNKNOWN)),
            ("Confidence", a.confidence, b.confidence),
        ],
    )
    lines = [
        f"# {a.company} vs {b.company}",
        "",
        table,
        "",
        "## Messaging themes",
        "",
        f"- **Shared:** {', '.join(label(t) for t in cmp.shared_themes) or 'none'}",
        f"- **Only {a.company}:** {', '.join(label(t) for t in cmp.only_a) or 'none'}",
        f"- **Only {b.company}:** {', '.join(label(t) for t in cmp.only_b) or 'none'}",
        "",
        "## Positioning wedge",
        "",
        cmp.wedge,
        "",
    ]
    return "\n".join(lines)
