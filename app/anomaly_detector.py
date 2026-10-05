from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from sklearn.ensemble import IsolationForest


FEATURES = (
    "cpu_usage_percent",
    "memory_usage_percent",
    "disk_usage_percent",
)


@dataclass(frozen=True)
class AnomalyResult:
    is_anomaly: bool
    anomaly_score: float


class ResourceAnomalyDetector:
    """Isolation Forest detector for system resource anomalies."""

    def __init__(
        self,
        contamination: float = 0.05,
        random_state: int = 42,
    ) -> None:
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
        )
        self._trained = False

    def fit(self, metrics: Iterable[dict]) -> None:
        rows = list(metrics)

        if len(rows) < 10:
            raise ValueError("At least 10 metric samples are required for training.")

        X = self._to_matrix(rows)
        self.model.fit(X)
        self._trained = True

    def predict(self, metrics: dict) -> AnomalyResult:
        if not self._trained:
            raise RuntimeError("Detector must be trained before prediction.")

        X = self._to_matrix([metrics])

        prediction = self.model.predict(X)[0]
        score = float(self.model.decision_function(X)[0])

        return AnomalyResult(
            is_anomaly=bool(prediction == -1),
            anomaly_score=score,
        )

    @staticmethod
    def _to_matrix(metrics: list[dict]) -> np.ndarray:
        try:
            return np.array(
                [
                    [float(metric[feature]) for feature in FEATURES]
                    for metric in metrics
                ],
                dtype=float,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Each metric must contain valid CPU, memory, and disk values."
            ) from exc
