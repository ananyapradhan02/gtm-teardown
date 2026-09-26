"""Snapshot store: dated, hashed records of a company's copy + classification.

* ``snapshot`` records a new entry unless the copy is byte-identical to the latest one
  (a no-op re-run must not pollute the timeline).
* ``diff`` compares the two most recent snapshots and reports **drift**: pricing model,
  GTM motion, or theme changes.
* ``watch`` runs snapshot+diff over a whole watchlist and keeps only drift above a
  significance bar: ``high`` = pricing or motion changed, ``medium`` = themes changed
  only, ``none`` = cosmetic copy edits.

The store is a single JSON file (default ``.gtm-teardown/snapshots.json``).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .classifier import Classification, label

DEFAULT_STORE = os.path.join(".gtm-teardown", "snapshots.json")

LEVELS = {"none": 0, "medium": 1, "high": 2}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class Snapshot:
    company: str
    taken_at: str
    sha: str
    chars: int
    pricing_model: str
    gtm_motion: str
    themes: List[str]

    @classmethod
    def from_classification(cls, c: Classification, text: str, taken_at: Optional[str] = None) -> "Snapshot":
        return cls(company=c.company,
                   taken_at=taken_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   sha=_hash(text), chars=len(text), pricing_model=c.pricing_model,
                   gtm_motion=c.gtm_motion, themes=list(c.themes))

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Drift:
    company: str
    before: Optional[Snapshot]
    after: Optional[Snapshot]
    pricing_changed: bool = False
    motion_changed: bool = False
    themes_added: List[str] = field(default_factory=list)
    themes_removed: List[str] = field(default_factory=list)
    copy_changed: bool = False
    baseline: bool = False  # True when this run created the first snapshot

    @property
    def level(self) -> str:
        if self.pricing_changed or self.motion_changed:
            return "high"
        if self.themes_added or self.themes_removed:
            return "medium"
        return "none"

    @property
    def has_drift(self) -> bool:
        return self.level != "none"

    def describe(self) -> str:
        if self.baseline:
            return f"{self.company}: baseline recorded (first snapshot) — nothing to compare yet."
        if self.before is None or self.after is None:
            return f"{self.company}: fewer than two snapshots — nothing to compare yet."
        if not self.copy_changed:
            return f"{self.company}: no change — copy identical to last snapshot ({self.after.taken_at})."
        parts = []
        if self.pricing_changed:
            parts.append(f"pricing {label(self.before.pricing_model)} → {label(self.after.pricing_model)}")
        if self.motion_changed:
            parts.append(f"motion {label(self.before.gtm_motion)} → {label(self.after.gtm_motion)}")
        if self.themes_added:
            parts.append("new themes: " + ", ".join(label(t) for t in self.themes_added))
        if self.themes_removed:
            parts.append("dropped themes: " + ", ".join(label(t) for t in self.themes_removed))
        if not parts:
            return f"{self.company}: copy changed but positioning held (cosmetic edit) — {self.before.taken_at} → {self.after.taken_at}."
        return f"{self.company} [{self.level.upper()}] {self.before.taken_at} → {self.after.taken_at}: " + "; ".join(parts)


class SnapshotStore:
    def __init__(self, path: str = DEFAULT_STORE):
        self.path = Path(path)
        self._data: Dict[str, List[dict]] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8") or "{}")

    # -- persistence ------------------------------------------------------- #
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    # -- queries ----------------------------------------------------------- #
    def _key(self, company: str) -> str:
        return company.strip().lower()

    def history(self, company: str) -> List[Snapshot]:
        return [Snapshot(**d) for d in self._data.get(self._key(company), [])]

    def latest(self, company: str) -> Optional[Snapshot]:
        h = self.history(company)
        return h[-1] if h else None

    def companies(self) -> List[str]:
        return [h[0]["company"] for h in self._data.values() if h]

    # -- writes ------------------------------------------------------------ #
    def snapshot(self, c: Classification, text: str, taken_at: Optional[str] = None) -> Tuple[Snapshot, bool]:
        """Record a snapshot. Returns (snapshot, created). Identical copy → (latest, False)."""
        latest = self.latest(c.company)
        if latest and latest.sha == _hash(text):
            return latest, False
        snap = Snapshot.from_classification(c, text, taken_at)
        self._data.setdefault(self._key(c.company), []).append(snap.to_dict())
        self.save()
        return snap, True

    # -- analysis ---------------------------------------------------------- #
    def diff(self, company: str) -> Drift:
        h = self.history(company)
        if len(h) < 2:
            return Drift(company=company, before=None, after=h[-1] if h else None)
        before, after = h[-2], h[-1]
        return Drift(
            company=after.company, before=before, after=after,
            pricing_changed=before.pricing_model != after.pricing_model,
            motion_changed=before.gtm_motion != after.gtm_motion,
            themes_added=[t for t in after.themes if t not in before.themes],
            themes_removed=[t for t in before.themes if t not in after.themes],
            copy_changed=before.sha != after.sha,
        )

    def track(self, c: Classification, text: str) -> Drift:
        """Snapshot then diff. A first-ever snapshot is a silent baseline, not drift."""
        had_history = bool(self.history(c.company))
        _, created = self.snapshot(c, text)
        if not had_history:
            d = self.diff(c.company)
            d.baseline = True
            return d
        if not created:
            latest = self.latest(c.company)
            return Drift(company=c.company, before=latest, after=latest, copy_changed=False)
        return self.diff(c.company)


def watch(store: SnapshotStore, items: Sequence[Tuple[Classification, str]], min_level: str = "medium") -> Tuple[List[Drift], List[Drift]]:
    """Track every (classification, copy) pair; return (significant, quiet) drift lists,
    significant sorted most-urgent-first."""
    threshold = LEVELS.get(min_level, 1)
    significant, quiet = [], []
    for c, text in items:
        d = store.track(c, text)
        (significant if (not d.baseline and LEVELS[d.level] >= threshold and threshold > 0) else quiet).append(d)
    significant.sort(key=lambda d: (-LEVELS[d.level], -(len(d.themes_added) + len(d.themes_removed)), d.company.lower()))
    return significant, quiet
