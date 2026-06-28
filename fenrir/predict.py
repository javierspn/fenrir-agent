"""Predict-before-solve + prediction error (002, T019). Constitution IV / FR-004/005.

A predicted outcome + confidence are recorded BEFORE the task is attempted. After
the sympy verdict, prediction_error is the blend of the verification delta
(predicted-vs-actual correctness) and the calibration gap (confidence vs realized).
PE is the master signal that gates downstream learning effort (Constitution IV).
"""
from __future__ import annotations

from dataclasses import dataclass

from fenrir.verify.sympy_oracle import SUCCEEDED


@dataclass
class Prediction:
    predicted_correct: bool
    confidence: float   # [0,1]


def realized_correct(verdict: str) -> float:
    """1.0 only on a sympy success; failed/unverified → 0.0 (unverified never a success)."""
    return 1.0 if verdict == SUCCEEDED else 0.0


def prediction_error(pred: Prediction, verdict: str) -> float:
    """PE ∈ [0,1] = 0.5·verification_delta + 0.5·calibration_gap (research R5)."""
    actual = realized_correct(verdict)
    verification_delta = abs((1.0 if pred.predicted_correct else 0.0) - actual)
    calibration_gap = abs(pred.confidence - actual)
    return 0.5 * verification_delta + 0.5 * calibration_gap


def parse_prediction(raw_text: str) -> Prediction:
    """Extract a coarse (predicted_correct, confidence) from the model's self-assessment.

    Expects a line like ``CONFIDENCE: 0.7``; defaults to a cold/low-confidence prediction
    when absent (which biases toward escalation on genuinely novel tasks)."""
    conf = 0.5
    for line in raw_text.splitlines():
        low = line.strip().lower()
        if low.startswith("confidence:"):
            try:
                conf = max(0.0, min(1.0, float(low.split(":", 1)[1].strip())))
            except ValueError:
                pass
    return Prediction(predicted_correct=conf >= 0.5, confidence=conf)
