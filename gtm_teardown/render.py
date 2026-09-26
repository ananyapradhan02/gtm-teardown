"""Render a single Classification as Markdown, JSON or a plain table."""

from __future__ import annotations

import json

from .classifier import Classification, label


def _ev_lines(evs, limit: int = 3) -> str:
    seen, out = set(), []
    for ev in evs:
        if ev.snippet in seen:
            continue
        seen.add(ev.snippet)
        out.append(f'  - "{ev.snippet}"')
        if len(out) >= limit:
            break
    return "\n".join(out) if out else "  - (no evidence)"


def to_markdown(c: Classification) -> str:
    parts = [
        f"# GTM teardown: {c.company}",
        "",
        f"- **Pricing model:** {label(c.pricing_model)}",
        f"- **GTM motion:** {label(c.gtm_motion)}",
        f"- **Messaging themes:** {', '.join(label(t) for t in c.themes) or 'none detected'}",
        f"- **Confidence:** {c.confidence} ({len(c.pricing_evidence) + len(c.motion_evidence) + len(c.theme_evidence)} evidence hits over {c.chars:,} chars)",
        f"- **Backend:** {c.backend}",
        "",
        "## Evidence",
        "",
        f"**Pricing → {label(c.pricing_model)}**",
        _ev_lines(c.pricing_evidence),
        "",
        f"**Motion → {label(c.gtm_motion)}**",
        _ev_lines(c.motion_evidence),
        "",
    ]
    counts = c.theme_counts()
    for theme in c.themes:
        parts += [f"**Theme → {label(theme)}** ({counts.get(theme, 0)} hits)", _ev_lines(c.evidence_for(theme)), ""]
    if c.negated:
        parts += ["## Ignored (negated) matches", ""]
        for ev in c.negated[:5]:
            parts.append(f'- ~~{label(ev.category)}~~ in "{ev.snippet}"')
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def to_json(c: Classification) -> str:
    return json.dumps(c.to_dict(), indent=2)


def to_table(c: Classification) -> str:
    rows = [
        ("company", c.company),
        ("pricing_model", label(c.pricing_model)),
        ("gtm_motion", label(c.gtm_motion)),
        ("themes", ", ".join(label(t) for t in c.themes) or "-"),
        ("confidence", c.confidence),
        ("backend", c.backend),
    ]
    w = max(len(k) for k, _ in rows)
    return "\n".join(f"{k:<{w}}  {v}" for k, v in rows)


def render(c: Classification, fmt: str = "md") -> str:
    if fmt == "json":
        return to_json(c)
    if fmt == "table":
        return to_table(c)
    return to_markdown(c)
