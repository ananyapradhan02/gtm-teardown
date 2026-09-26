"""Classification backends.

* ``HeuristicBackend`` – regex/negation classifier in :mod:`classifier`. Always available.
* ``LLMBackend``       – asks Claude (Anthropic API) for the same schema, then validates
                          it. Requires the ``anthropic`` package and ``ANTHROPIC_API_KEY``.

``get_backend(use_llm=True)`` returns an LLM backend that **auto-falls back** to the
heuristic one on any failure (no key, no package, bad JSON, API error) and records the
reason in ``Classification.backend`` so a report never silently pretends.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from .classifier import (
    GTM_MOTIONS,
    PRICING_MODELS,
    THEMES,
    UNKNOWN,
    Classification,
    Evidence,
    classify_text,
)

DEFAULT_MODEL = os.environ.get("GTM_TEARDOWN_MODEL", "claude-sonnet-5")

_LLM_PROMPT = """You are a go-to-market analyst. Classify the company's public marketing copy.

Return ONLY a JSON object with these keys:
- "pricing_model": one of {pricing}
- "gtm_motion": one of {motions}
- "themes": a list (strongest first, max 5) drawn from {themes}
- "evidence": an object mapping each chosen category to ONE short verbatim quote from the copy
Use "unknown" when the copy gives no real evidence. Never infer from a company's reputation.

Company: {company}
Copy:
\"\"\"
{text}
\"\"\""""


class HeuristicBackend:
    name = "heuristic"

    def classify(self, company: str, text: str) -> Classification:
        return classify_text(company, text)


class LLMBackend:
    name = "llm"

    def __init__(self, model: str = DEFAULT_MODEL, fallback: Optional[HeuristicBackend] = None):
        self.model = model
        self.fallback = fallback or HeuristicBackend()

    # -- helpers ----------------------------------------------------------- #
    def _call(self, company: str, text: str) -> dict:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError("anthropic package not installed (pip install anthropic)") from exc
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model,
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": _LLM_PROMPT.format(
                    pricing=list(PRICING_MODELS) + [UNKNOWN],
                    motions=list(GTM_MOTIONS) + [UNKNOWN],
                    themes=list(THEMES),
                    company=company,
                    text=text[:12000],
                ),
            }],
        )
        raw = "".join(getattr(block, "text", "") for block in msg.content)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end < 0:
            raise ValueError("model did not return JSON")
        return json.loads(raw[start:end + 1])

    @staticmethod
    def _validate(company: str, text: str, data: dict) -> Classification:
        pricing = data.get("pricing_model", UNKNOWN)
        motion = data.get("gtm_motion", UNKNOWN)
        themes = [t for t in data.get("themes", []) if t in THEMES]
        if pricing not in PRICING_MODELS:
            pricing = UNKNOWN
        if motion not in GTM_MOTIONS:
            motion = UNKNOWN
        evidence = data.get("evidence", {}) or {}
        result = Classification(company=company, pricing_model=pricing, gtm_motion=motion,
                                themes=themes, backend="llm", chars=len(text))

        def ev(cat: str) -> Evidence:
            return Evidence(category=cat, snippet=str(evidence.get(cat, ""))[:140], pattern="llm")

        if pricing != UNKNOWN:
            result.pricing_evidence = [ev(pricing)]
        if motion != UNKNOWN:
            result.motion_evidence = [ev(motion)]
        result.theme_evidence = [ev(t) for t in themes]
        return result

    # -- public ------------------------------------------------------------ #
    def classify(self, company: str, text: str) -> Classification:
        try:
            data = self._call(company, text)
            return self._validate(company, text, data)
        except Exception as exc:  # noqa: BLE001 - any failure must fall back, loudly
            reason = f"{type(exc).__name__}: {exc}"[:120]
            print(f"[gtm-teardown] LLM backend unavailable ({reason}); using heuristic backend.",
                  file=sys.stderr)
            result = self.fallback.classify(company, text)
            result.backend = f"heuristic (llm fallback: {reason})"
            return result


def get_backend(use_llm: bool = False, model: str = DEFAULT_MODEL):
    return LLMBackend(model=model) if use_llm else HeuristicBackend()
