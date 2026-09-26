"""Prose outputs: the landscape ``report`` and the ``essay`` draft.

Both work from a batch of classifications. ``report`` is a one-page Markdown write-up of
the distribution (pricing / motion / themes) with an "essay seed" takeaway; ``essay`` goes
further and drafts a full multi-section essay with bracketed [spans] marking where the
author's own argument and voice still have to go.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from .classifier import UNKNOWN, Classification, label
from .rank import Scored, rank_rows
from .sources import md_table


# --------------------------------------------------------------------------- #
# Distribution helpers
# --------------------------------------------------------------------------- #

@dataclass
class Landscape:
    n: int
    pricing: Counter
    motion: Counter
    themes: Counter
    no_signal: List[str]


def landscape(cs: Sequence[Classification]) -> Landscape:
    return Landscape(
        n=len(cs),
        pricing=Counter(c.pricing_model for c in cs),
        motion=Counter(c.gtm_motion for c in cs),
        themes=Counter(t for c in cs for t in c.themes),
        no_signal=[c.company for c in cs if not c.has_signal],
    )


def dominant(counter: Counter) -> Tuple[Optional[str], int]:
    """The most common *real* classification. Never returns 'unknown' (Day 7 regression):
    'unknown' is the absence of a signal, so it can't be a dominant pattern."""
    real = [(k, v) for k, v in counter.most_common() if k != UNKNOWN]
    if not real:
        return None, 0
    return real[0]


def _dominance_sentence(kind: str, counter: Counter, n: int) -> str:
    key, count = dominant(counter)
    unknown_n = counter.get(UNKNOWN, 0)
    if key is None:
        return f"None of the {n} companies gives a readable {kind} signal in the copy sampled."
    share = f"{count} of {n}"
    if unknown_n > count:
        return (f"Where the {kind} is readable at all, {label(key)} leads ({share}), "
                f"but {unknown_n} of {n} companies give no {kind} signal — the bigger finding is the silence.")
    return f"The dominant {kind} is {label(key)} ({share})."


def _pct(count: int, n: int) -> str:
    return f"{(100 * count / n):.0f}%" if n else "0%"


def _dist_table(counter: Counter, n: int, col: str) -> str:
    rows = [(label(k), v, _pct(v, n)) for k, v in counter.most_common()]
    return md_table([col, "companies", "share"], rows)


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def essay_seed(cs: Sequence[Classification]) -> str:
    """One paragraph naming the open positioning wedge in this landscape."""
    ls = landscape(cs)
    p_key, _ = dominant(ls.pricing)
    m_key, _ = dominant(ls.motion)
    top_theme = ls.themes.most_common(1)[0][0] if ls.themes else None
    claimed = set(ls.themes)
    from .classifier import THEMES  # local import keeps module import light
    unclaimed = [t for t in THEMES if t not in claimed]
    bits = []
    if p_key and m_key:
        bits.append(f"Most of this set sells {label(p_key)} through a {label(m_key)} motion")
    elif p_key:
        bits.append(f"Most of this set sells {label(p_key)}")
    elif m_key:
        bits.append(f"Most of this set runs a {label(m_key)} motion")
    else:
        bits.append("This set gives almost no readable pricing or motion signal")
    if top_theme:
        bits.append(f"and everyone leans on {label(top_theme)} ({ls.themes[top_theme]} of {ls.n} companies)")
    seed = ", ".join(bits) + "."
    if unclaimed:
        seed += (f" The uncontested ground is {label(unclaimed[0])}"
                 + (f" and {label(unclaimed[1])}" if len(unclaimed) > 1 else "")
                 + ": nobody in this sample claims it, which is either a market that doesn't care or a position waiting to be taken.")
    else:
        seed += " Every theme is already claimed by someone; the wedge, if there is one, is in proof, not in positioning."
    return seed


def render_report(cs: Sequence[Classification], title: str = "GTM landscape") -> str:
    ls = landscape(cs)
    lines = [
        f"# {title}",
        "",
        f"*{ls.n} companies · generated {date.today().isoformat()} · gtm-teardown*",
        "",
        "## Pricing models",
        "",
        _dist_table(ls.pricing, ls.n, "pricing model"),
        "",
        _dominance_sentence("pricing model", ls.pricing, ls.n),
        "",
        "## GTM motions",
        "",
        _dist_table(ls.motion, ls.n, "motion"),
        "",
        _dominance_sentence("GTM motion", ls.motion, ls.n),
        "",
        "## Messaging themes",
        "",
        md_table(["theme", "companies claiming it", "share"],
                 [(label(k), v, _pct(v, ls.n)) for k, v in ls.themes.most_common()]) if ls.themes
        else "_No messaging themes detected._",
        "",
        "## Company table",
        "",
        md_table(["company", "pricing", "motion", "top theme", "confidence"],
                 [(c.company, label(c.pricing_model), label(c.gtm_motion),
                   label(c.top_theme() or UNKNOWN), c.confidence) for c in cs]),
        "",
        "## Takeaway (essay seed)",
        "",
        essay_seed(cs),
        "",
    ]
    if ls.no_signal:
        lines += [f"_No usable signal for: {', '.join(ls.no_signal)}. Feed them more copy (pricing page, docs intro)._", ""]
    return "\n".join(lines)


def render_rank_report(scored: Sequence[Scored], rubric_name: str, title: str = "ICP ranking") -> str:
    headers, rows = rank_rows(scored)
    return "\n".join([
        f"# {title}",
        "",
        f"*rubric: {rubric_name} · {len(scored)} companies · generated {date.today().isoformat()}*",
        "",
        md_table(headers, rows),
        "",
    ])


# --------------------------------------------------------------------------- #
# essay
# --------------------------------------------------------------------------- #

def _pull_claim(c: Classification) -> Optional[str]:
    """The strongest verbatim snippet we have for a company."""
    for pool in (c.theme_evidence, c.motion_evidence, c.pricing_evidence):
        if pool:
            return pool[0].snippet
    return None


def pick_vignettes(cs: Sequence[Classification], k: int = 3) -> List[Classification]:
    """2–3 companies worth a paragraph: the most-evidenced, and the odd one out if any."""
    with_signal = [c for c in cs if c.has_signal]
    ordered = sorted(with_signal, key=lambda c: -(len(c.pricing_evidence) + len(c.motion_evidence) + len(c.theme_evidence)))
    picks = ordered[: max(0, k - 1)]
    ls = landscape(cs)
    m_key, _ = dominant(ls.motion)
    odd = next((c for c in ordered if c.gtm_motion not in (m_key, UNKNOWN) and c not in picks), None)
    if odd:
        picks.append(odd)
    elif len(ordered) > len(picks):
        picks.append(ordered[len(picks)])
    return picks[:k]


def render_essay(cs: Sequence[Classification], title: str | None = None, author: str = "Ananya Pradhan") -> str:
    ls = landscape(cs)
    p_key, p_n = dominant(ls.pricing)
    m_key, m_n = dominant(ls.motion)
    top = ls.themes.most_common(3)
    title = title or (f"Everyone in agentic AI is selling {label(top[0][0])}. Nobody is proving it."
                      if top else "What the copy of agentic-AI companies gives away")
    vignettes = pick_vignettes(cs)

    lines = [f"# {title}", "", f"*Draft generated by gtm-teardown from {ls.n} companies' public copy. "
             f"Bracketed [spans] are where {author}'s argument has to go. Nothing here is publishable as-is.*", ""]

    # Hook
    lines += ["## Hook", ""]
    if top:
        lines.append(f"{top[0][1]} of the {ls.n} agentic-AI companies I read this week lead with {label(top[0][0])}. "
                     f"[One sentence on why that surprised you, or why it didn't.]")
    else:
        lines.append(f"I read the public copy of {ls.n} agentic-AI companies this week. [What you expected to find, in one line.]")
    lines.append("")

    # Landscape body
    lines += ["## The landscape", ""]
    lines.append(_dominance_sentence("pricing model", ls.pricing, ls.n) + " " + _dominance_sentence("GTM motion", ls.motion, ls.n))
    if top:
        lines.append("The three themes that carry the category's messaging: " +
                     "; ".join(f"{label(k)} ({v} of {ls.n})" for k, v in top) + ".")
    lines.append("[Your read: is this convergence rational (the buyer really wants this) or lazy (everyone copied the leader)?]")
    lines.append("")

    # Vignettes
    lines += ["## Three companies, read closely", ""]
    for c in vignettes:
        claim = _pull_claim(c)
        lines.append(f"**{c.company}** — {label(c.pricing_model)}, {label(c.gtm_motion)}, leads with {label(c.top_theme() or UNKNOWN)}.")
        if claim:
            lines.append(f'Their own words: "{claim}"')
        lines.append(f"[What this choice tells you about who {c.company} thinks the buyer is, and what it costs them.]")
        lines.append("")
    if not vignettes:
        lines += ["[No company in this batch had enough signal for a vignette — add pricing-page copy and re-run.]", ""]

    # Thesis
    lines += ["## The thesis", ""]
    lines.append(essay_seed(cs))
    lines.append("[State the claim in one sentence you'd defend on a call. Then the strongest objection, then why it's wrong.]")
    lines.append("")

    # Sign-off
    lines += ["## Sign-off", "",
              f"[One line that tells the reader what to do with this — or what you're doing with it.]", "",
              f"— {author}", ""]
    return "\n".join(lines)
