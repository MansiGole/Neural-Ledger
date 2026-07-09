import numpy as np
from sklearn.ensemble import IsolationForest

VALID_STATUSES = ["initiated", "processing", "completed", "failed"]
STATUS_ORDINAL = {s: i for i, s in enumerate(VALID_STATUSES)}


class AnomalyDetector:
    def __init__(self):
        self._model: IsolationForest | None = None

    def train(self, contamination: float = 0.1) -> None:
        rng = np.random.default_rng(42)
        n_normal = 900
        n_outlier = 100

        # Normal: amount 100-10000 cents, delay 0-5s, status 0-3
        normal = np.column_stack([
            rng.integers(100, 10_001, n_normal),
            rng.uniform(0, 5, n_normal),
            rng.integers(0, 4, n_normal),
        ])
        # Outliers: extreme amounts, large delays
        outliers = np.column_stack([
            rng.integers(1_000_000, 10_000_001, n_outlier),
            rng.uniform(3600, 86400, n_outlier),
            rng.integers(0, 4, n_outlier),
        ])
        X = np.vstack([normal, outliers]).astype(float)

        try:
            self._model = IsolationForest(contamination=contamination, random_state=42)
            self._model.fit(X)
        except Exception as exc:
            raise RuntimeError(f"Anomaly detector training failed: {exc}") from exc

    def score(self, payload: dict) -> tuple[float, bool]:
        if self._model is None:
            raise RuntimeError("Model not trained. Call train() first.")

        amount_cents = float(payload.get("amount_cents") or 0)
        delay_seconds = float(payload.get("delay_seconds") or 0)
        status = payload.get("status", "initiated")
        status_ordinal = float(STATUS_ORDINAL.get(status, 0))

        features = np.array([[amount_cents, delay_seconds, status_ordinal]])
        raw_score = float(self._model.score_samples(features)[0])
        prediction = self._model.predict(features)[0]
        is_anomaly = prediction == -1
        return raw_score, is_anomaly
