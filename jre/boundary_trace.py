"""Stigmergic boundary traces for unresolved judgment-readiness signals.

This module is intentionally dependency-light. It borrows the useful shape of a
pheromone-style trace substrate: signals are deposited, reinforced, opposed,
decayed, searched, and retracted. The trace field is advisory only. It can raise
review pressure or suggest missing evidence, but it cannot authorize a clinical
disposition or clear deterministic guardrails.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4


ACTIVE_STATUS = "active"
RETRACTED_STATUS = "retracted"
EXPIRED_STATUS = "expired"

TRACE_CLAIM = "CLAIM"
TRACE_CONSTRAINT = "CONSTRAINT"
TRACE_SIGNAL = "SIGNAL"
TRACE_QUESTION = "QUESTION"
TRACE_OUTCOME = "OUTCOME"
TRACE_RETRACTION = "RETRACTION"

RISK_TRACE_TYPES = {TRACE_CLAIM, TRACE_CONSTRAINT, TRACE_SIGNAL, TRACE_OUTCOME}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _normalize_keys(keys: Optional[Iterable[str]]) -> tuple[str, ...]:
    if not keys:
        return ()
    normalized = {str(key).strip().lower() for key in keys if str(key).strip()}
    return tuple(sorted(normalized))


def _normalize_patch_type(patch_type: str) -> str:
    return str(patch_type).strip().upper()


@dataclass
class BoundaryTracePatch:
    """One bounded memory trace in the uncertainty boundary field."""

    patch_type: str
    concept: str
    payload: Dict[str, Any] = field(default_factory=dict)
    symbolic_keys: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.5
    decay_rate: float = 0.05
    support_mass: float = 0.0
    opposition_mass: float = 0.0
    evidence_ids: List[str] = field(default_factory=list)
    target_id: Optional[str] = None
    created_by: str = "system"
    patch_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = ACTIVE_STATUS
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.patch_type = _normalize_patch_type(self.patch_type)
        self.symbolic_keys = _normalize_keys(self.symbolic_keys)
        self.confidence = _clamp(self.confidence)
        self.decay_rate = max(0.0, float(self.decay_rate))
        self.support_mass = max(0.0, float(self.support_mass))
        self.opposition_mass = max(0.0, float(self.opposition_mass))

    @property
    def net_support(self) -> float:
        return self.support_mass - self.opposition_mass

    @property
    def support_ratio(self) -> float:
        total = self.support_mass + self.opposition_mass
        if total <= 0:
            return 1.0
        return self.support_mass / total

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE_STATUS

    def effective_strength(self, now: Optional[datetime] = None) -> float:
        """Return review pressure from confidence, support, opposition, and age."""

        if self.status != ACTIVE_STATUS:
            return 0.0
        if now is None:
            now = _utcnow()
        elapsed_days = max(0.0, (now - self.created_at).total_seconds() / 86400.0)
        age_factor = math.exp(-self.decay_rate * elapsed_days)
        support_factor = 1.0 + self.support_mass
        opposition_factor = 1.0 + self.opposition_mass
        return self.confidence * age_factor * support_factor / opposition_factor

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


class BoundaryTraceField:
    """In-memory trace field for unresolved Any Dispo/JRE boundary signals."""

    def __init__(self) -> None:
        self.patches: Dict[str, BoundaryTracePatch] = {}
        self.events: List[Dict[str, Any]] = []

    def apply_patch(
        self,
        patch_type: str,
        concept: str,
        payload: Optional[Dict[str, Any]] = None,
        symbolic_keys: Optional[Sequence[str]] = None,
        confidence: float = 0.5,
        decay_rate: float = 0.05,
        created_by: str = "system",
        evidence_ids: Optional[Sequence[str]] = None,
        target_id: Optional[str] = None,
    ) -> BoundaryTracePatch:
        patch = BoundaryTracePatch(
            patch_type=patch_type,
            concept=concept,
            payload=dict(payload or {}),
            symbolic_keys=_normalize_keys(symbolic_keys),
            confidence=confidence,
            decay_rate=decay_rate,
            created_by=created_by,
            evidence_ids=list(evidence_ids or []),
            target_id=target_id,
        )
        self.patches[patch.patch_id] = patch
        self._record_event("apply", patch.patch_id, actor=created_by)
        return patch

    def reinforce(
        self,
        patch_id: str,
        magnitude: float = 1.0,
        direction: str = "support",
        actor: str = "system",
        evidence_ids: Optional[Sequence[str]] = None,
    ) -> BoundaryTracePatch:
        patch = self._require_patch(patch_id)
        if patch.status != ACTIVE_STATUS:
            raise ValueError(f"cannot reinforce non-active patch {patch_id!r}")

        delta = max(0.0, float(magnitude))
        normalized_direction = str(direction).strip().lower()
        if normalized_direction in {"support", "supports", "positive"}:
            patch.support_mass += delta
        elif normalized_direction in {"oppose", "opposes", "opposition", "negative"}:
            patch.opposition_mass += delta
        else:
            raise ValueError("direction must be 'support' or 'oppose'")

        for evidence_id in evidence_ids or []:
            if evidence_id not in patch.evidence_ids:
                patch.evidence_ids.append(evidence_id)
        patch.updated_at = _utcnow()
        self._record_event(
            "reinforce",
            patch_id,
            actor=actor,
            direction=normalized_direction,
            magnitude=delta,
        )
        return patch

    def oppose(
        self,
        patch_id: str,
        magnitude: float = 1.0,
        actor: str = "system",
        evidence_ids: Optional[Sequence[str]] = None,
    ) -> BoundaryTracePatch:
        return self.reinforce(
            patch_id,
            magnitude=magnitude,
            direction="oppose",
            actor=actor,
            evidence_ids=evidence_ids,
        )

    def decay(self, ticks: float = 1.0, expire_below: Optional[float] = None) -> int:
        """Apply deterministic trace decay and optionally expire weak traces."""

        expired = 0
        for patch in self.patches.values():
            if patch.status != ACTIVE_STATUS:
                continue
            decay_factor = math.exp(-patch.decay_rate * max(0.0, float(ticks)))
            patch.support_mass *= decay_factor
            patch.opposition_mass *= decay_factor
            patch.updated_at = _utcnow()
            if expire_below is not None and patch.effective_strength() < expire_below:
                patch.status = EXPIRED_STATUS
                expired += 1
                self._record_event("expire", patch.patch_id, actor="decay")
        self._record_event("decay", None, actor="system", ticks=max(0.0, float(ticks)))
        return expired

    def retract(
        self,
        patch_id: str,
        reason: str = "",
        actor: str = "system",
    ) -> BoundaryTracePatch:
        patch = self._require_patch(patch_id)
        patch.status = RETRACTED_STATUS
        patch.updated_at = _utcnow()
        self._record_event("retract", patch_id, actor=actor, reason=reason)
        return self.apply_patch(
            patch_type=TRACE_RETRACTION,
            concept=patch.concept,
            payload={"reason": reason, "retracted_patch_id": patch_id},
            symbolic_keys=patch.symbolic_keys,
            confidence=1.0,
            decay_rate=patch.decay_rate,
            created_by=actor,
            target_id=patch_id,
        )

    def search(
        self,
        symbolic_keys: Optional[Sequence[str]] = None,
        concept: Optional[str] = None,
        patch_type: Optional[str] = None,
        min_strength: float = 0.0,
        include_inactive: bool = False,
    ) -> List[BoundaryTracePatch]:
        query_keys = set(_normalize_keys(symbolic_keys))
        normalized_type = _normalize_patch_type(patch_type) if patch_type else None
        results: List[BoundaryTracePatch] = []

        for patch in self.patches.values():
            if not include_inactive and not patch.is_active:
                continue
            if normalized_type and patch.patch_type != normalized_type:
                continue
            if concept and patch.concept != concept:
                continue
            if query_keys and not query_keys.intersection(patch.symbolic_keys):
                continue
            if patch.effective_strength() < min_strength:
                continue
            results.append(patch)

        results.sort(
            key=lambda item: (item.effective_strength(), item.net_support, item.confidence),
            reverse=True,
        )
        return results

    def risk_pressure(
        self,
        symbolic_keys: Optional[Sequence[str]] = None,
        concept: Optional[str] = None,
    ) -> float:
        traces = self.search(symbolic_keys=symbolic_keys, concept=concept)
        return sum(
            patch.effective_strength()
            for patch in traces
            if patch.patch_type in RISK_TRACE_TYPES
        )

    def summary(self, top_n: int = 5) -> Dict[str, Any]:
        active = [patch for patch in self.patches.values() if patch.is_active]
        key_counts: Dict[str, int] = {}
        for patch in active:
            for key in patch.symbolic_keys:
                key_counts[key] = key_counts.get(key, 0) + 1
        top_keys = sorted(key_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n]
        top_traces = sorted(active, key=lambda patch: patch.effective_strength(), reverse=True)[:top_n]
        return {
            "patch_count": len(self.patches),
            "active_patch_count": len(active),
            "retracted_patch_count": sum(1 for patch in self.patches.values() if patch.status == RETRACTED_STATUS),
            "expired_patch_count": sum(1 for patch in self.patches.values() if patch.status == EXPIRED_STATUS),
            "risk_pressure": self.risk_pressure(),
            "top_symbolic_keys": [{"key": key, "count": count} for key, count in top_keys],
            "top_traces": [patch.to_dict() for patch in top_traces],
        }

    def _require_patch(self, patch_id: str) -> BoundaryTracePatch:
        try:
            return self.patches[patch_id]
        except KeyError as exc:
            raise KeyError(f"unknown boundary trace patch {patch_id!r}") from exc

    def _record_event(
        self,
        event_type: str,
        patch_id: Optional[str],
        actor: str,
        **metadata: Any,
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "patch_id": patch_id,
                "actor": actor,
                "timestamp": _utcnow().isoformat(),
                "metadata": metadata,
            }
        )
