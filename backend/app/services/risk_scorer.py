from math import isfinite


def score_risk(
    ml_score: float,
    iam_risk: float,
    resource_impact: float,
    cost_impact: float,
    traffic_anomaly: float,
) -> dict[str, float | str]:
    """Combine a 0–1 ML score and four 0–100 incident factors."""
    factors = (
        ("ml_score", ml_score, 1.0, 0.30),
        ("iam_risk", iam_risk, 100.0, 0.25),
        ("resource_impact", resource_impact, 100.0, 0.20),
        ("cost_impact", cost_impact, 100.0, 0.15),
        ("traffic_anomaly", traffic_anomaly, 100.0, 0.10),
    )
    risk_score = 0.0
    for name, value, maximum, weight in factors:
        if not isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be between 0 and {maximum:g}.")
        risk_score += 100 * weight * value / maximum

    risk_score = round(risk_score, 2)
    severity = next(
        level for minimum, level in (
            (85, "critical"), (65, "high"), (40, "medium"), (0, "low")
        )
        if risk_score >= minimum
    )
    return {"risk_score": risk_score, "severity": severity}
