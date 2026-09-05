"""Confidence scoring: weighted sum of six sub-scores (0-100 each).

Weights follow the specification:
technical confluence 40%, historical backtest performance 20%, regime
alignment 15%, sector strength 10%, volume confirmation 5%, macro/earnings
risk 10%.
"""
from __future__ import annotations

WEIGHTS = {
    "technical": 0.40,
    "backtest": 0.20,
    "regime": 0.15,
    "sector": 0.10,
    "volume": 0.05,
    "macro": 0.10,
}

COMPONENT_KEYS = tuple(WEIGHTS.keys())


def compute_confidence(subs: dict[str, float]) -> float:
    """Weighted sum of the sub-scores, clamped to 0-100 and rounded to 1dp."""
    score = 0.0
    for key, weight in WEIGHTS.items():
        score += weight * _clamp(subs.get(key, 50.0))
    return round(score, 1)


def confidence_label(score: float) -> str:
    if score >= 71:
        return "High"
    if score >= 41:
        return "Medium"
    return "Low"


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))
