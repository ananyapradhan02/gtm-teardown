"""Heuristic, negation-aware classifier for public GTM copy.

Given a company's public copy (homepage, pricing page, docs intro), it classifies:

* ``pricing_model``  – usage_based | tiered_saas | seat_based | custom_quote | unknown
* ``gtm_motion``     – self_serve | sales_led | hybrid | unknown
* ``themes``         – the messaging themes the copy leans on (roi_cost_savings,
                       ease_of_use, security_compliance, ...)

Design rules learned the hard way (each one has a named regression test):

1. Patterns are matched **per clause**, never across sentence or clause boundaries.
   Clause boundaries are sentence punctuation, ``;``, ``:``, ``--``, em/en dashes and
   newlines. A negation cue in a previous sentence must never flip a later match.
2. A match is **negated** only if a negation cue ("no", "not", "never", "without",
   "don't", ...) appears within a few words *before* it in the same clause.
   "no self-serve plans" is not self-serve evidence.
3. A bare keyword is not evidence. "enterprise" alone does not imply tiered plans;
   only "enterprise plan/tier" or "tiered plans" does.
4. Regexes that "look right" are tested against real vendor phrasing, including
   verb inflections ("saving 40%", "saved 40%") and inserted words
   ("save *you* 30%", "talk to our sales *team* for pricing").
5. Phrases that both motions use ("up and running in minutes") are **themes**,
   not motion evidence. Counting them as motion evidence manufactures "hybrid".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #

PRICING_MODELS = ("usage_based", "tiered_saas", "seat_based", "custom_quote")
GTM_MOTIONS = ("self_serve", "sales_led", "hybrid")
THEMES = (
    "roi_cost_savings",
    "ease_of_use",
    "security_compliance",
    "speed_time_to_value",
    "accuracy_reliability",
    "integration_ecosystem",
    "autonomy_agents",
    "human_in_the_loop",
    "scale_enterprise",
)
UNKNOWN = "unknown"

HUMAN_LABELS = {
    "usage_based": "usage-based",
    "tiered_saas": "tiered SaaS plans",
    "seat_based": "per-seat",
    "custom_quote": "custom quote / contact sales",
    "self_serve": "self-serve (product-led)",
    "sales_led": "sales-led",
    "hybrid": "hybrid (self-serve + sales)",
    "roi_cost_savings": "ROI / cost savings",
    "ease_of_use": "ease of use",
    "security_compliance": "security & compliance",
    "speed_time_to_value": "speed / time to value",
    "accuracy_reliability": "accuracy & reliability",
    "integration_ecosystem": "integrations & ecosystem",
    "autonomy_agents": "autonomy / agents",
    "human_in_the_loop": "human in the loop",
    "scale_enterprise": "scale & enterprise readiness",
    UNKNOWN: "unknown (no signal)",
}


def label(key: str) -> str:
    return HUMAN_LABELS.get(key, key)


# --------------------------------------------------------------------------- #
# Patterns.  Every entry: (name, compiled regex).  All case-insensitive.
# --------------------------------------------------------------------------- #

def _rx(*parts: str) -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in parts]


PRICING_PATTERNS: Dict[str, List[re.Pattern]] = {
    "usage_based": _rx(
        r"\busage[- ]based\b",
        r"\bpay[- ]as[- ]you[- ]go\b",
        r"\bconsumption[- ]based\b",
        r"\bmetered\b",
        r"\bpay (?:only )?for what you (?:use|need)\b",
        r"\bper (?:token|api call|call|request|minute|message|conversation|resolution|task|run|action|outcome)s?\b",
        r"\bcredit[- ]based\b",
        r"\boutcome[- ]based pricing\b",
    ),
    "tiered_saas": _rx(
        # Day 7: "Tiered plans: Starter, Explorer, Pro, Enterprise" must match.
        r"\btiered (?:pricing|plans?)\b",
        # Day 2: a bare "enterprise" is NOT evidence; "enterprise plan/tier" is.
        r"\b(?:starter|basic|free|pro|professional|team|business|growth|plus|premium|scale|enterprise)\s+(?:plan|tier)s?\b",
        r"\bplans? (?:start|starting) (?:at|from)\b",
        r"\b\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/|per)\s*(?:mo|month|year|yr)\b",
        r"\bfree (?:plan|tier|forever)\b",
        r"\b(?:monthly|annual) (?:and|or) (?:annual|monthly) (?:plans|billing)\b",
        r"\bchoose (?:a|your|the right) plan\b",
        r"\bcompare plans\b",
        r"\bpricing tiers?\b",
        r"\bupgrade (?:to|anytime)\b",
    ),
    "seat_based": _rx(
        r"\bper[- ](?:seat|user|editor|member)\b",
        r"\bseat[- ]based\b",
        r"\b\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/|per)\s*(?:seat|user)\b",
        r"\bunlimited (?:seats|users)\b",
    ),
    "custom_quote": _rx(
        r"\bcustom (?:pricing|quotes?)\b",
        r"\benterprise pricing\b",
        r"\bpricing (?:is )?(?:available )?(?:on|upon) request\b",
        r"\b(?:get|request) (?:a )?(?:custom )?quote\b",
        # Day 10: "talk to our sales team for pricing" (inserted "team").
        r"\btalk(?:ing)? (?:to|with) (?:our |the )?(?:sales|team)(?: team)? (?:for|about|to get|to discuss) (?:a quote|pricing|custom pricing)\b",
        r"\bcontact (?:us|sales|our (?:sales )?team)\b[^.;:]{0,40}?\bpricing\b",
        r"\bpricing\b[^.;:]{0,40}?\bcontact (?:us|sales|our (?:sales )?team)\b",
        r"\bpricing\b[^.;:]{0,40}?\btalk to (?:sales|our (?:sales )?team)\b",
    ),
}

MOTION_PATTERNS: Dict[str, List[re.Pattern]] = {
    "self_serve": _rx(
        r"\bself[- ]serve\b",
        r"\bself[- ]service\b",
        r"\bproduct[- ]led\b",
        r"\b(?:sign|signing) up (?:for )?free\b",
        r"\bsign up (?:and|to) (?:start|get|build)\b",
        r"\bstart (?:for )?free\b",
        r"\bget started (?:for )?free\b",
        r"\bfree trial\b",
        r"\btry (?:it )?(?:for )?free\b",
        r"\bno credit card (?:required|needed)\b",
        r"\bcreate (?:an|your) (?:free )?account\b",
        r"\bstart building\b",
        r"\bget an api key\b",
        # Day 12: "up and running in minutes" deliberately absent — it's a theme
        # (ease_of_use), not motion evidence; sales-led vendors say it too.
    ),
    "sales_led": _rx(
        r"\b(?:book|schedule|request|get) (?:a )?(?:live |personalized |custom )?demo\b",
        # Day 6: broadened — "talk to our sales team", "talking to sales".
        r"\btalk(?:ing)? (?:to|with) (?:our |the |a |an )?(?:sales|team|expert|specialist|solutions engineer)(?: team)?\b",
        r"\bspeak (?:to|with) (?:an? |our )?(?:expert|specialist|sales|team)\b",
        r"\bcontact sales\b",
        r"\bget in touch with (?:our )?(?:sales|team)\b",
        # Day 7: bare noun phrase "(our/an/a/the/dedicated) sales team".
        r"\b(?:our|an|a|the|dedicated) sales team\b",
        r"\bsales[- ](?:led|assisted)\b",
        r"\bwhite[- ]glove\b",
        r"\bdedicated (?:account|customer success|implementation) (?:manager|team|partner)\b",
        r"\bimplementation (?:team|partner|services)\b",
        r"\benterprise sales\b",
        r"\bprocurement\b",
        r"\bRFPs?\b",
        r"\b(?:custom|tailored) (?:deployment|implementation|rollout|onboarding)\b",
    ),
}

THEME_PATTERNS: Dict[str, List[re.Pattern]] = {
    "roi_cost_savings": _rx(
        r"\bROI\b",
        # Day 4 (\d+), Day 8 ("save you 30%", "save customers 40%"),
        # Day 10 ("saving 40%", "saved 40%"): verb inflection + up to 3 inserted words.
        r"\bsav(?:e|es|ed|ing)\b(?:\s+\w+){0,3}?\s+\d+\s?%",
        r"\bcost savings?\b",
        r"\b(?:reduc|cut|lower)(?:e|es|ed|ing|s)?\b(?:\s+\w+){0,3}?\s+costs?\b",
        r"\bpayback\b",
        r"\b\d+x (?:roi|return)\b",
        r"\bcheaper\b",
        r"\blower (?:total )?cost of ownership\b",
        r"\b\d+\s?% (?:cheaper|lower cost|cost reduction)\b",
    ),
    "ease_of_use": _rx(
        r"\bno[- ]code\b",
        r"\blow[- ]code\b",
        r"\beasy to (?:use|set up|deploy)\b",
        r"\bup and running in (?:minutes|hours|a day)\b",
        r"\bin minutes\b",
        r"\bintuitive\b",
        r"\bdrag[- ]and[- ]drop\b",
        r"\bout of the box\b",
        r"\bplug[- ]and[- ]play\b",
        r"\bno (?:setup|configuration|training|engineering) (?:required|needed)\b",
        r"\bzero (?:setup|configuration)\b",
    ),
    "security_compliance": _rx(
        r"\bSOC ?2\b",
        r"\bHIPAA\b",
        r"\bGDPR\b",
        r"\bISO ?27001\b",
        r"\bFedRAMP\b",
        r"\benterprise[- ]grade security\b",
        r"\bcomplian(?:ce|t)\b",
        r"\bdata (?:privacy|residency|governance)\b",
        r"\baudit (?:logs?|trails?)\b",
        r"\bencrypt(?:ed|ion)\b",
        r"\bSSO\b",
        r"\bzero data retention\b",
        r"\bpermissions? (?:model|controls?)\b",
        r"\brole[- ]based access\b",
    ),
    "speed_time_to_value": _rx(
        r"\b\d+x faster\b",
        r"\bfaster\b",
        r"\bin (?:seconds|hours|days)\b",
        r"\bwithin (?:minutes|hours|days)\b",
        r"\bdeploy(?:ed|s)? in (?:days|weeks)\b",
        r"\btime[- ]to[- ]value\b",
        r"\bgo live in\b",
        r"\binstant(?:ly)?\b",
        r"\breal[- ]time\b",
        r"\b(?:same|next)[- ]day\b",
    ),
    "accuracy_reliability": _rx(
        r"\baccura(?:cy|te|tely)\b",
        r"\bhallucinat\w*",
        r"\breliab\w*",
        r"\b\d+(?:\.\d+)?\s?% (?:accuracy|precision|resolution rate|containment)\b",
        r"\bguardrails?\b",
        r"\bevals?\b",
        r"\bevaluations?\b",
        r"\bgrounded\b",
        r"\bcitations?\b",
        r"\bdeterministic\b",
        r"\bverif(?:y|ied|ies|iable)\b",
        r"\bobservability\b",
    ),
    "integration_ecosystem": _rx(
        r"\bintegrat(?:es?|ion|ions|ed)\b",
        r"\bAPIs?\b",
        r"\bSDKs?\b",
        r"\bMCP\b",
        r"\bworks with (?:your )?(?:existing )?(?:stack|tools|systems|crm|data)\b",
        r"\b(?:Salesforce|HubSpot|Slack|Zendesk|Snowflake|Workday|SAP|ServiceNow|Jira|Notion|Shopify|Intercom)\b",
        r"\bconnectors?\b",
        r"\bwebhooks?\b",
        r"\bplugs? into\b",
        r"\b\d+\+? integrations\b",
    ),
    "autonomy_agents": _rx(
        r"\bagentic\b",
        r"\bautonomous(?:ly)?\b",
        r"\bAI (?:agents?|employees?|workers?|teammates?|coworkers?|workforce)\b",
        r"\bagents? (?:that|which|who)\b",
        r"\bdigital (?:workers?|employees?|teammates?)\b",
        r"\bend[- ]to[- ]end\b",
        r"\bhands[- ]off\b",
        r"\bwithout human (?:intervention|input|involvement)\b",
        r"\bmulti[- ]agent\b",
        r"\bautopilot\b",
        r"\bresolves?\b(?:\s+\w+){0,3}?\s+(?:on its own|automatically|autonomously)\b",
    ),
    "human_in_the_loop": _rx(
        r"\bhuman[- ]in[- ]the[- ]loop\b",
        r"\bhuman (?:review|oversight|approval|handoff|escalation|judgment)\b",
        r"\bescalat(?:e|es|ed|ion) to (?:a )?(?:human|person|your team|an agent)\b",
        r"\bcopilot\b",
        r"\bassists? your (?:team|reps|agents)\b",
        r"\bkeeps? (?:humans|people|your team) in (?:control|the loop)\b",
        r"\bapproval workflows?\b",
        r"\breview before\b",
        r"\bsuggest(?:s|ed)? (?:replies|actions|next steps)\b",
    ),
    "scale_enterprise": _rx(
        r"\benterprise[- ](?:ready|grade|scale)\b",
        r"\bfor enterprises?\b",
        r"\benterprise (?:teams|customers|deployments|companies|workflows)\b",
        r"\bFortune ?\d+\b",
        r"\bat scale\b",
        r"\bmillions of\b",
        r"\bglobal (?:teams|enterprises|deployments|brands)\b",
        r"\btrusted by\b",
        r"\b\d[\d,]*\+? (?:customers|companies|teams|enterprises|brands|organizations)\b",
    ),
}

NEGATION_CUES = (
    "no",
    "not",
    "never",
    "without",
    "isn't",
    "aren't",
    "don't",
    "doesn't",
    "won't",
    "can't",
    "cannot",
    "instead of",
    "rather than",
    "skip",
    "skipping",
)
_NEGATION_RX = re.compile(
    r"(?<![\w-])(?:" + "|".join(re.escape(c) for c in NEGATION_CUES) + r")(?![\w-])",
    re.IGNORECASE,
)
NEGATION_WINDOW_WORDS = 5

# Clause boundaries: sentence punctuation (but not a decimal point), ";", ":",
# "--", em/en dashes, a spaced hyphen, newlines.  Day 6 + Day 8 regression tests.
_CLAUSE_SPLIT_RX = re.compile(r"(?<!\d)\.(?!\d)|[!?;:\n]|--|—|–|\s-\s|\|")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class Evidence:
    category: str  # e.g. "usage_based" or "roi_cost_savings"
    snippet: str  # the clause the match was found in
    pattern: str  # the regex source that matched


@dataclass
class Classification:
    company: str
    pricing_model: str = UNKNOWN
    gtm_motion: str = UNKNOWN
    themes: List[str] = field(default_factory=list)
    pricing_evidence: List[Evidence] = field(default_factory=list)
    motion_evidence: List[Evidence] = field(default_factory=list)
    theme_evidence: List[Evidence] = field(default_factory=list)
    negated: List[Evidence] = field(default_factory=list)
    backend: str = "heuristic"
    chars: int = 0

    # ----- convenience -------------------------------------------------- #
    @property
    def has_signal(self) -> bool:
        return (
            self.pricing_model != UNKNOWN
            or self.gtm_motion != UNKNOWN
            or bool(self.themes)
        )

    @property
    def confidence(self) -> str:
        n = len(self.pricing_evidence) + len(self.motion_evidence) + len(self.theme_evidence)
        if n == 0:
            return "none"
        if n <= 2:
            return "low"
        if n <= 5:
            return "medium"
        return "high"

    def theme_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for ev in self.theme_evidence:
            counts[ev.category] = counts.get(ev.category, 0) + 1
        return counts

    def top_theme(self) -> str | None:
        return self.themes[0] if self.themes else None

    def evidence_for(self, category: str) -> List[Evidence]:
        pool = self.pricing_evidence + self.motion_evidence + self.theme_evidence
        return [e for e in pool if e.category == category]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["has_signal"] = self.has_signal
        d["confidence"] = self.confidence
        return d


# --------------------------------------------------------------------------- #
# Core matching
# --------------------------------------------------------------------------- #

def split_clauses(text: str) -> List[str]:
    """Split copy into clauses. Negation never crosses a clause boundary."""
    return [c.strip() for c in _CLAUSE_SPLIT_RX.split(text) if c and c.strip()]


def is_negated(clause: str, match_start: int) -> bool:
    """True if a negation cue sits within NEGATION_WINDOW_WORDS words before the match,
    inside this clause only."""
    prefix = clause[:match_start]
    words = prefix.split()
    window = " ".join(words[-NEGATION_WINDOW_WORDS:])
    return bool(_NEGATION_RX.search(window))


def _scan(text: str, patterns: Dict[str, List[re.Pattern]]) -> Tuple[Dict[str, List[Evidence]], List[Evidence]]:
    """Return {category: [evidence...]} for non-negated hits, plus the negated hits."""
    hits: Dict[str, List[Evidence]] = {k: [] for k in patterns}
    negated: List[Evidence] = []
    for clause in split_clauses(text):
        snippet = clause if len(clause) <= 140 else clause[:137] + "..."
        for category, rxs in patterns.items():
            for rx in rxs:
                m = rx.search(clause)
                if not m:
                    continue
                ev = Evidence(category=category, snippet=snippet, pattern=rx.pattern)
                if is_negated(clause, m.start()):
                    negated.append(ev)
                else:
                    hits[category].append(ev)
    return hits, negated


def _pick(hits: Dict[str, List[Evidence]], priority: Tuple[str, ...]) -> str:
    best, best_n = UNKNOWN, 0
    for cat in priority:  # priority order breaks ties deterministically
        n = len(hits.get(cat, []))
        if n > best_n:
            best, best_n = cat, n
    return best


def classify_text(company: str, text: str) -> Classification:
    """Heuristic classification of one company's public copy."""
    text = text or ""
    result = Classification(company=company.strip() or "unknown", chars=len(text))

    p_hits, p_neg = _scan(text, PRICING_PATTERNS)
    m_hits, m_neg = _scan(text, MOTION_PATTERNS)
    t_hits, t_neg = _scan(text, THEME_PATTERNS)
    result.negated = p_neg + m_neg + t_neg

    # Pricing: most evidence wins; ties resolved by specificity.
    result.pricing_model = _pick(p_hits, ("custom_quote", "usage_based", "seat_based", "tiered_saas"))
    result.pricing_evidence = p_hits.get(result.pricing_model, [])

    # Motion: hybrid only when BOTH sides have real evidence (Day 12).
    ss, sl = m_hits["self_serve"], m_hits["sales_led"]
    if ss and sl:
        result.gtm_motion = "hybrid"
        result.motion_evidence = ss + sl
    elif ss:
        result.gtm_motion, result.motion_evidence = "self_serve", ss
    elif sl:
        result.gtm_motion, result.motion_evidence = "sales_led", sl

    # Themes: every theme with at least one non-negated hit, strongest first.
    ranked = sorted(((k, v) for k, v in t_hits.items() if v), key=lambda kv: (-len(kv[1]), kv[0]))
    result.themes = [k for k, _ in ranked]
    result.theme_evidence = [ev for _, evs in ranked for ev in evs]
    return result
