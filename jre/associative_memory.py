"""Associative near-miss memory for boundary-shape recall.

The implementation is a deterministic stand-in for a VAMS/Hopfield-style memory
layer. Partial case signatures recall prior near-miss shapes by key overlap.
Confirmed useful recalls strengthen the pattern; rejected recalls weaken it.
The output is intentionally advisory: missing nodes, falsifiers, and review
actions for deterministic validators to inspect.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4


ADVISORY_AUTHORITY = "advisory_only"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _normalize_keys(keys: Iterable[str]) -> tuple[str, ...]:
    normalized = {str(key).strip().lower() for key in keys if str(key).strip()}
    return tuple(sorted(normalized))


@dataclass
class NearMissPattern:
    """Reusable boundary-failure shape, stripped of PHI and free text."""

    signature_keys: tuple[str, ...]
    recommended_actions: List[str]
    missing_nodes: List[str] = field(default_factory=list)
    falsifiers: List[str] = field(default_factory=list)
    outcome: str = "near_miss"
    strength: float = 0.5
    success_count: int = 0
    failure_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.signature_keys = _normalize_keys(self.signature_keys)
        self.strength = _clamp(self.strength)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass
class RecallResult:
    """One advisory memory recall from a partial case signature."""

    pattern: NearMissPattern
    overlap_keys: tuple[str, ...]
    missing_signature_keys: tuple[str, ...]
    similarity: float
    score: float
    authority: str = ADVISORY_AUTHORITY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.pattern.memory_id,
            "overlap_keys": list(self.overlap_keys),
            "missing_signature_keys": list(self.missing_signature_keys),
            "similarity": self.similarity,
            "score": self.score,
            "authority": self.authority,
            "pattern": self.pattern.to_dict(),
        }


class NearMissMemory:
    """Small associative memory for sparse Any Dispo/JRE boundary signatures."""

    def __init__(self, patterns: Optional[Sequence[NearMissPattern]] = None) -> None:
        self.patterns: Dict[str, NearMissPattern] = {}
        for pattern in patterns or []:
            self.patterns[pattern.memory_id] = pattern

    def store(
        self,
        signature_keys: Sequence[str],
        recommended_actions: Sequence[str],
        missing_nodes: Optional[Sequence[str]] = None,
        falsifiers: Optional[Sequence[str]] = None,
        outcome: str = "near_miss",
        strength: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> NearMissPattern:
        pattern = NearMissPattern(
            signature_keys=_normalize_keys(signature_keys),
            recommended_actions=list(recommended_actions),
            missing_nodes=list(missing_nodes or []),
            falsifiers=list(falsifiers or []),
            outcome=outcome,
            strength=strength,
            metadata=dict(metadata or {}),
            memory_id=memory_id or str(uuid4()),
        )
        self.patterns[pattern.memory_id] = pattern
        return pattern

    def recall(
        self,
        signature_keys: Sequence[str],
        k: int = 5,
        min_score: float = 0.0,
    ) -> List[RecallResult]:
        query = set(_normalize_keys(signature_keys))
        if not query:
            return []

        recalls: List[RecallResult] = []
        for pattern in self.patterns.values():
            pattern_keys = set(pattern.signature_keys)
            if not pattern_keys:
                continue
            overlap = query.intersection(pattern_keys)
            if not overlap:
                continue
            union = query.union(pattern_keys)
            similarity = len(overlap) / len(union)
            score = similarity * pattern.strength
            if score < min_score:
                continue
            recalls.append(
                RecallResult(
                    pattern=pattern,
                    overlap_keys=tuple(sorted(overlap)),
                    missing_signature_keys=tuple(sorted(pattern_keys.difference(query))),
                    similarity=similarity,
                    score=score,
                )
            )

        recalls.sort(key=lambda item: (item.score, item.similarity, item.pattern.strength), reverse=True)
        return recalls[: max(0, int(k))]

    def suggest(
        self,
        signature_keys: Sequence[str],
        k: int = 5,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        recalls = self.recall(signature_keys=signature_keys, k=k, min_score=min_score)
        return {
            "authority": ADVISORY_AUTHORITY,
            "recall_count": len(recalls),
            "memory_ids": [recall.pattern.memory_id for recall in recalls],
            "missing_nodes": self._merge_unique(recall.pattern.missing_nodes for recall in recalls),
            "falsifiers": self._merge_unique(recall.pattern.falsifiers for recall in recalls),
            "recommended_actions": self._merge_unique(recall.pattern.recommended_actions for recall in recalls),
            "pattern_completion": self._merge_unique(recall.missing_signature_keys for recall in recalls),
            "recalls": [recall.to_dict() for recall in recalls],
        }

    def strengthen(self, memory_id: str, amount: float = 0.1) -> NearMissPattern:
        pattern = self._require_pattern(memory_id)
        pattern.strength = _clamp(pattern.strength + max(0.0, float(amount)))
        pattern.success_count += 1
        pattern.updated_at = _utcnow()
        return pattern

    def weaken(self, memory_id: str, amount: float = 0.1) -> NearMissPattern:
        pattern = self._require_pattern(memory_id)
        pattern.strength = _clamp(pattern.strength - max(0.0, float(amount)))
        pattern.failure_count += 1
        pattern.updated_at = _utcnow()
        return pattern

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_count": len(self.patterns),
            "authority": ADVISORY_AUTHORITY,
            "patterns": [pattern.to_dict() for pattern in self.patterns.values()],
        }

    @staticmethod
    def _merge_unique(items: Iterable[Iterable[str]]) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()
        for group in items:
            for item in group:
                key = str(item).strip()
                if not key or key.lower() in seen:
                    continue
                seen.add(key.lower())
                merged.append(key)
        return merged

    def _require_pattern(self, memory_id: str) -> NearMissPattern:
        try:
            return self.patterns[memory_id]
        except KeyError as exc:
            raise KeyError(f"unknown near-miss memory {memory_id!r}") from exc
