"""Turn a teardown finding into a personalised cold-outreach opener.

Hook priority: messaging theme > GTM motion > pricing model. A theme is the most
specific thing a company chose to say about itself; motion and pricing are structural
and read as less personal. If there is no signal at all, ``draft_opener`` returns
``None`` — it never invents a hook, because a generic opener is worse than no opener.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .classifier import UNKNOWN, Classification, label

_THEME_HOOKS = {
    "roi_cost_savings": "you lead with the savings number rather than the model — that's a buyer-side choice most agentic-AI companies still don't make",
    "ease_of_use": "you sell ease of setup in a category that mostly sells capability — a deliberate bet that the buyer is tired, not curious",
    "security_compliance": "you put compliance above capability on the page, which tells me who actually signs your contracts",
    "speed_time_to_value": "you lead with time-to-value, which is the one claim the buyer can verify inside a pilot",
    "accuracy_reliability": "you talk about evals and accuracy on the homepage — most of the category hides that in the docs",
    "integration_ecosystem": "you lead with the stack you plug into rather than the model you run — a workflow positioning, not an AI one",
    "autonomy_agents": "you're one of the few that says 'autonomous' without flinching, which changes what the buyer expects from a pilot",
    "human_in_the_loop": "you position humans-in-the-loop as the feature, not the caveat — the opposite of most of the category",
    "scale_enterprise": "you lead with logos and scale rather than the product, which usually means a sales-led motion behind the page",
}

_MOTION_HOOKS = {
    "self_serve": "you run fully self-serve in a category that's mostly sales-led — I'm curious what your activation-to-paid looks like",
    "sales_led": "you're sales-led with no self-serve path, which is a strong stance when most of the category is hedging with a free tier",
    "hybrid": "you run both a self-serve path and a sales motion — I'd bet the interesting number is which one your best accounts came through",
}

_PRICING_HOOKS = {
    "usage_based": "you price on usage, which is honest about how agents create value and hard to forecast for a buyer — how are you handling that objection?",
    "seat_based": "you price per seat for an agent product, which is the one model that gets cheaper for you the more the product works",
    "tiered_saas": "you've packaged agents into classic SaaS tiers — the plans read like software, not headcount, which I suspect is deliberate",
    "custom_quote": "your pricing is quote-only, which tells me the deals are big enough that packaging would cost you money",
}


@dataclass
class Opener:
    company: str
    hook_type: str  # theme | motion | pricing
    hook_key: str
    line: str
    evidence: Optional[str]


def draft_opener(c: Classification, sender_context: str | None = None) -> Optional[Opener]:
    """Return an Opener, or None when there is no usable signal."""
    top = c.top_theme()
    if top and top in _THEME_HOOKS:
        hook_type, key, body = "theme", top, _THEME_HOOKS[top]
        ev = c.evidence_for(top)
    elif c.gtm_motion != UNKNOWN and c.gtm_motion in _MOTION_HOOKS:
        hook_type, key, body = "motion", c.gtm_motion, _MOTION_HOOKS[c.gtm_motion]
        ev = c.motion_evidence
    elif c.pricing_model != UNKNOWN and c.pricing_model in _PRICING_HOOKS:
        hook_type, key, body = "pricing", c.pricing_model, _PRICING_HOOKS[c.pricing_model]
        ev = c.pricing_evidence
    else:
        return None
    line = f"Read the {c.company} site this week — {body}."
    if sender_context:
        line += f" {sender_context.strip()}"
    return Opener(company=c.company, hook_type=hook_type, hook_key=key, line=line,
                  evidence=ev[0].snippet if ev else None)


def render_opener(op: Optional[Opener], company: str) -> str:
    if op is None:
        return (f"No opener for {company}: the copy gave no usable signal (no theme, motion or pricing "
                f"evidence). Refusing to invent a hook — feed it the pricing page or docs intro and re-run.")
    lines = [f"**{op.company}** — hook: {op.hook_type} / {label(op.hook_key)}", "", op.line]
    if op.evidence:
        lines += ["", f'_Grounded in their copy: "{op.evidence}"_']
    return "\n".join(lines)
