
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "cpu_utilization",
    "network_in_bytes",
    "network_out_bytes",
    "request_count",
]


class MLDetector:
    def __init__(self, contamination=0.05, threshold=0.70, random_state=42):
        self.contamination = contamination
        self.threshold = threshold
        self.random_state = random_state
        self.pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", IsolationForest(
                n_estimators=200,
                contamination=contamination,
                random_state=random_state,
            )),
        ])
        self.is_fitted = False
        self.score_center = None
        self.score_scale = None

    def _prepare(self, records):
        frame = pd.DataFrame(records)
        missing = [f for f in FEATURES if f not in frame.columns]

        if missing:
            raise ValueError(f"Missing required features: {missing}")

        values = frame[FEATURES].apply(pd.to_numeric, errors="coerce")

        if values.isnull().any().any():
            raise ValueError("Features contain missing or non-numeric values.")

        if (values < 0).any().any():
            raise ValueError("Features must be non-negative.")

        return np.log1p(values.to_numpy(dtype=float))

    def fit(self, records):
        frame = pd.DataFrame(records)

        if "is_anomalous" in frame.columns:
            frame = frame[frame["is_anomalous"] == False]

        if len(frame) < 10:
            raise ValueError("At least 10 normal records are required.")

        X_train = self._prepare(frame)
        self.pipeline.fit(X_train)

        scores = self.pipeline.decision_function(X_train)
        self.score_center = float(np.percentile(scores, 5))
        self.score_scale = max(float(np.std(scores)), 0.05)

        self.is_fitted = True
        return self

    def predict(self, records):
        if not self.is_fitted:
            raise RuntimeError("The detector must be fitted before prediction.")

        frame = pd.DataFrame(records)
        X = self._prepare(frame)

        decision_scores = self.pipeline.decision_function(X)
        anomaly_scores = 1.0 / (
            1.0 + np.exp(np.clip(
                (decision_scores - self.score_center) / self.score_scale,
                -50,
                50,
            ))
        )

        results = frame.copy()
        results["anomaly_score"] = np.clip(anomaly_scores, 0.0, 1.0)
        results["is_anomaly_predicted"] = (
            results["anomaly_score"] >= self.threshold
        )

        return results

    def predict_one(self, record):
        return self.predict([record]).iloc[0].to_dict()

import pandas as pd

def score_metrics(baseline_rows, target_rows) -> list[float]:
    """Fit on normal baseline rows and return one score per target row."""
    baseline = pd.DataFrame(baseline_rows)
    targets = pd.DataFrame(target_rows)
    if targets.empty:
        return []
    if baseline.empty:
        raise ValueError("At least one baseline row is required.")

    detector = MLDetector()
    detector.fit(baseline.to_dict("records"))
    predictions = pd.DataFrame(detector.predict(targets.to_dict("records")))
    return predictions["anomaly_score"].astype(float).tolist()
