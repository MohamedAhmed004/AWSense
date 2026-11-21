"""Pure-Python multi-signal event correlation engine for AWSense."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.entities import AlertSeverity

_HIGH_RISK_CLOUDTRAIL_EVENTS = {
    "ConsoleLogin",
    "CreateAccessKey",
    "AttachUserPolicy",
    "PutUserPolicy",
    "CreateUser",
    "AssumeRole",
    "AuthorizeSecurityGroupIngress",
    "RunInstances",
    "StopLogging",
    "DeleteTrail",
    "ModifyDBInstance",
    "PutBucketPolicy",
}

_TRAFFIC_METRIC_TOKENS = (
    "request",
    "traffic",
    "bot",
    "network",
    "rpm",
    "rps",
    "egress",
    "bandwidth",
)


class CloudTrailEvent(BaseModel):
    """Normalized CloudTrail / IAM audit signal input."""

    event_id: str
    timestamp: datetime | str
    event_name: str
    region: str
    principal: str = "unknown"
    resource_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    source_ip: str | None = None
    is_anomalous: bool = False
    risk_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricSpike(BaseModel):
    """Telemetry utilization or traffic spike signal input."""

    event_id: str
    timestamp: datetime | str
    resource_id: str
    metric_name: str
    value: float
    baseline: float = 0.0
    region: str | None = None
    anomaly_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostDelta(BaseModel):
    """Billing / Cost Explorer anomaly delta signal input."""

    event_id: str
    timestamp: datetime | str
    service: str
    delta_usd: float
    baseline_usd: float = 0.0
    delta_pct: float | None = None
    resource_id: str | None = None
    region: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CorrelatedSignal(BaseModel):
    """Unified internal representation of any telemetry/audit/cost signal."""

    signal_type: Literal["cloudtrail", "metric_spike", "cost_delta"]
    event_id: str
    timestamp: datetime
    resource_ids: list[str] = Field(default_factory=list)
    region: str | None = None
    principal: str | None = None
    summary: str
    severity_weight: float = Field(ge=0.0, le=1.0)
    raw: dict[str, Any] = Field(default_factory=dict)


class SignalBreakdown(BaseModel):
    """Factor breakdown for a correlated incident (factor scores on 0.0-100.0 scale)."""

    cloudtrail_count: int
    metric_spike_count: int
    cost_delta_count: int
    iam_risk: float
    resource_impact: float
    cost_impact: float
    traffic_anomaly: float
    total_cost_delta_usd: float


class CorrelatedIncident(BaseModel):
    """Unified multi-signal incident emitted by the correlation engine."""

    incident_id: str
    incident_type: str
    title: str
    severity: AlertSeverity
    risk_score: float = Field(ge=0.0, le=100.0)
    primary_resource_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    principals: list[str] = Field(default_factory=list)
    window_start: datetime
    window_end: datetime
    correlated_event_ids: list[str] = Field(default_factory=list)
    signal_breakdown: SignalBreakdown
    signals: list[CorrelatedSignal] = Field(default_factory=list)
    summary: str
    recommended_actions: list[str] = Field(default_factory=list)


def parse_timestamp(value: datetime | str) -> datetime:
    """Parse an ISO-8601 string or datetime into a UTC-aware datetime."""
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith(("Z", "z")):
            raw = f"{raw[:-1]}+00:00"
        dt = datetime.fromisoformat(raw)
    elif isinstance(value, datetime):
        dt = value
    else:
        raise TypeError(f"Expected datetime or ISO-8601 string, got {type(value).__name__}")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _dedupe_preserve_order(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item is None:
            continue
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _is_known_principal(principal: str | None) -> bool:
    return bool(principal and principal.strip() and principal.strip().lower() != "unknown")


def _cloudtrail_weight(event: CloudTrailEvent) -> float:
    if event.risk_hint is not None:
        return _clamp(event.risk_hint)
    weight = 0.30
    if event.is_anomalous:
        weight += 0.35
    if event.event_name in _HIGH_RISK_CLOUDTRAIL_EVENTS:
        weight += 0.25
    return _clamp(weight)


def _metric_weight(spike: MetricSpike) -> float:
    if spike.anomaly_score is not None:
        return _clamp(spike.anomaly_score)
    if spike.baseline > 0:
        ratio = max(0.0, (spike.value - spike.baseline) / spike.baseline)
        weight = 0.25 + min(0.75, ratio / 4.0)
    else:
        weight = 0.55 if spike.value > 0 else 0.20

    metric_lower = spike.metric_name.lower()
    if ("cpu" in metric_lower or "utilization" in metric_lower) and spike.value >= 80.0:
        weight = max(weight, 0.75)
    return _clamp(weight)


def _cost_weight(delta: CostDelta) -> float:
    if delta.delta_pct is not None:
        pct = max(0.0, delta.delta_pct)
    elif delta.baseline_usd > 0:
        pct = max(0.0, (delta.delta_usd / delta.baseline_usd) * 100.0)
    else:
        pct = min(300.0, max(0.0, delta.delta_usd))

    usd_component = min(1.0, max(0.0, delta.delta_usd) / 500.0)
    pct_component = min(1.0, pct / 200.0)
    return _clamp(0.20 + 0.40 * usd_component + 0.40 * pct_component)


def normalize_signals(
    cloudtrail_events: Iterable[CloudTrailEvent | dict[str, Any]] = (),
    metric_spikes: Iterable[MetricSpike | dict[str, Any]] = (),
    cost_deltas: Iterable[CostDelta | dict[str, Any]] = (),
) -> list[CorrelatedSignal]:
    """Normalize heterogeneous input events into chronologically sorted CorrelatedSignals."""
    signals: list[CorrelatedSignal] = []

    for raw_ct in cloudtrail_events:
        event = raw_ct if isinstance(raw_ct, CloudTrailEvent) else CloudTrailEvent.model_validate(raw_ct)
        ts = parse_timestamp(event.timestamp)
        resource_ids = _dedupe_preserve_order([event.resource_id, *event.resource_ids])
        principal = event.principal.strip() if event.principal and event.principal.strip() else None
        ip_suffix = f" from {event.source_ip}" if event.source_ip else ""
        signals.append(
            CorrelatedSignal(
                signal_type="cloudtrail",
                event_id=event.event_id,
                timestamp=ts,
                resource_ids=resource_ids,
                region=event.region.strip() or None,
                principal=principal,
                summary=f"CloudTrail {event.event_name} by {principal or 'unknown'}{ip_suffix} in {event.region}",
                severity_weight=round(_cloudtrail_weight(event), 4),
                raw=event.model_dump(mode="json"),
            )
        )

    for raw_metric in metric_spikes:
        spike = raw_metric if isinstance(raw_metric, MetricSpike) else MetricSpike.model_validate(raw_metric)
        ts = parse_timestamp(spike.timestamp)
        resource_ids = _dedupe_preserve_order([spike.resource_id])
        signals.append(
            CorrelatedSignal(
                signal_type="metric_spike",
                event_id=spike.event_id,
                timestamp=ts,
                resource_ids=resource_ids,
                region=spike.region.strip() if spike.region and spike.region.strip() else None,
                principal=None,
                summary=(
                    f"{spike.metric_name} spiked to {spike.value:.1f} "
                    f"(baseline {spike.baseline:.1f}) on {spike.resource_id}"
                ),
                severity_weight=round(_metric_weight(spike), 4),
                raw=spike.model_dump(mode="json"),
            )
        )

    for raw_cost in cost_deltas:
        delta = raw_cost if isinstance(raw_cost, CostDelta) else CostDelta.model_validate(raw_cost)
        ts = parse_timestamp(delta.timestamp)
        resource_ids = _dedupe_preserve_order([delta.resource_id])
        pct_text = f" ({delta.delta_pct:+.1f}%)" if delta.delta_pct is not None else ""
        signals.append(
            CorrelatedSignal(
                signal_type="cost_delta",
                event_id=delta.event_id,
                timestamp=ts,
                resource_ids=resource_ids,
                region=delta.region.strip() if delta.region and delta.region.strip() else None,
                principal=None,
                summary=f"{delta.service} spend delta +${delta.delta_usd:.2f}{pct_text}",
                severity_weight=round(_cost_weight(delta), 4),
                raw=delta.model_dump(mode="json"),
            )
        )

    signals.sort(key=lambda sig: (sig.timestamp, sig.signal_type, sig.event_id))
    return signals


def _regions_compatible(region_a: str | None, region_b: str | None) -> bool:
    return region_a is None or region_b is None or region_a == region_b


def signals_are_related(a: CorrelatedSignal, b: CorrelatedSignal, max_gap: timedelta) -> bool:
    """Return True if two signals fall within max_gap and share resource, principal, or region scope."""
    if abs(a.timestamp - b.timestamp) > max_gap:
        return False

    if set(a.resource_ids) & set(b.resource_ids):
        return True

    if (
        a.signal_type == "cloudtrail"
        and b.signal_type == "cloudtrail"
        and _is_known_principal(a.principal)
        and _is_known_principal(b.principal)
        and a.principal == b.principal
        and _regions_compatible(a.region, b.region)
    ):
        return True

    if a.region and b.region and a.region == b.region and (not a.resource_ids or not b.resource_ids):
        return True

    return False


class _Cluster:
    """Mutable working cluster used internally during chronological grouping."""

    def __init__(self, initial: CorrelatedSignal) -> None:
        self.signals: list[CorrelatedSignal] = [initial]
        self.start: datetime = initial.timestamp
        self.end: datetime = initial.timestamp
        self.resource_ids: set[str] = set(initial.resource_ids)
        self.principals_by_region: set[tuple[str, str | None]] = set()
        self.regions: set[str] = set()
        self._index_signal(initial)

    def _index_signal(self, signal: CorrelatedSignal) -> None:
        self.resource_ids.update(signal.resource_ids)
        if signal.region:
            self.regions.add(signal.region)
        if signal.signal_type == "cloudtrail" and _is_known_principal(signal.principal):
            assert signal.principal is not None
            self.principals_by_region.add((signal.principal, signal.region))

    def add(self, signal: CorrelatedSignal) -> None:
        self.signals.append(signal)
        if signal.timestamp < self.start:
            self.start = signal.timestamp
        if signal.timestamp > self.end:
            self.end = signal.timestamp
        self._index_signal(signal)

    def merge_from(self, other: _Cluster) -> None:
        for sig in other.signals:
            self.add(sig)

    def can_fit_timestamp(self, ts: datetime, max_gap: timedelta) -> bool:
        new_start = min(self.start, ts)
        new_end = max(self.end, ts)
        return (new_end - new_start) <= max_gap

    def match_priority(self, signal: CorrelatedSignal, max_gap: timedelta) -> int | None:
        """Return 1 (resource), 2 (principal), 3 (region-level), or None if unrelated."""
        if not self.can_fit_timestamp(signal.timestamp, max_gap):
            return None

        if signal.resource_ids and (self.resource_ids & set(signal.resource_ids)):
            return 1

        if signal.signal_type == "cloudtrail" and _is_known_principal(signal.principal):
            for existing_principal, existing_region in self.principals_by_region:
                if existing_principal == signal.principal and _regions_compatible(
                    existing_region, signal.region
                ):
                    return 2

        # Region-level match is only permitted when either the signal or the cluster
        # lacks specific resource IDs; two disjoint resource-pinned scopes must not merge.
        if signal.region and signal.region in self.regions:
            if not signal.resource_ids or not self.resource_ids:
                return 3

        return None


def _is_traffic_metric(signal: CorrelatedSignal) -> bool:
    if signal.signal_type != "metric_spike":
        return False
    metric_name = str(signal.raw.get("metric_name", "")).lower()
    return any(token in metric_name for token in _TRAFFIC_METRIC_TOKENS)


def _score_cluster(signals: list[CorrelatedSignal]) -> tuple[SignalBreakdown, float, AlertSeverity]:
    ct_signals = [s for s in signals if s.signal_type == "cloudtrail"]
    metric_signals = [s for s in signals if s.signal_type == "metric_spike"]
    cost_signals = [s for s in signals if s.signal_type == "cost_delta"]

    iam_risk = 0.0
    if ct_signals:
        peak_ct = max(s.severity_weight for s in ct_signals) * 100.0
        iam_risk = min(100.0, peak_ct + max(0, len(ct_signals) - 1) * 5.0)

    traffic_signals = [s for s in metric_signals if _is_traffic_metric(s)]
    non_traffic_metrics = [s for s in metric_signals if not _is_traffic_metric(s)]

    traffic_anomaly = (
        min(100.0, max(s.severity_weight for s in traffic_signals) * 100.0)
        if traffic_signals
        else 0.0
    )

    compute_weights = [s.severity_weight for s in non_traffic_metrics]
    if not compute_weights and traffic_signals:
        # High traffic/network spikes also impose compute/bandwidth resource pressure.
        compute_weights = [s.severity_weight * 0.85 for s in traffic_signals]
    if any(s.raw.get("event_name") in {"RunInstances", "ModifyDBInstance"} for s in ct_signals):
        compute_weights.append(0.80)

    resource_impact = min(100.0, max(compute_weights) * 100.0) if compute_weights else 0.0

    total_cost_delta_usd = sum(float(s.raw.get("delta_usd", 0.0)) for s in cost_signals)
    cost_impact = (
        min(100.0, max(s.severity_weight for s in cost_signals) * 100.0) if cost_signals else 0.0
    )

    active_scores = [
        score for score in (iam_risk, resource_impact, cost_impact, traffic_anomaly) if score > 0.0
    ]
    if not active_scores:
        base_score = 0.0
    else:
        peak = max(active_scores)
        mean = sum(active_scores) / len(active_scores)
        base_score = 0.55 * peak + 0.45 * mean

    distinct_sources = len({s.signal_type for s in signals})
    diversity_bonus = 8.0 * max(0, distinct_sources - 1)
    volume_bonus = min(10.0, 2.0 * max(0, len(signals) - 2))
    risk_score = round(_clamp(base_score + diversity_bonus + volume_bonus, 0.0, 100.0), 1)

    if risk_score >= 85.0:
        severity = AlertSeverity.CRITICAL
    elif risk_score >= 65.0:
        severity = AlertSeverity.HIGH
    elif risk_score >= 40.0:
        severity = AlertSeverity.MEDIUM
    else:
        severity = AlertSeverity.LOW

    breakdown = SignalBreakdown(
        cloudtrail_count=len(ct_signals),
        metric_spike_count=len(metric_signals),
        cost_delta_count=len(cost_signals),
        iam_risk=round(iam_risk, 1),
        resource_impact=round(resource_impact, 1),
        cost_impact=round(cost_impact, 1),
        traffic_anomaly=round(traffic_anomaly, 1),
        total_cost_delta_usd=round(total_cost_delta_usd, 2),
    )
    return breakdown, risk_score, severity


def _classify_incident(
    signals: list[CorrelatedSignal],
    breakdown: SignalBreakdown,
) -> tuple[str, str, str, list[str]]:
    has_traffic_spike = any(_is_traffic_metric(s) for s in signals)
    resource_ids = _dedupe_preserve_order(rid for s in signals for rid in s.resource_ids)
    regions = _dedupe_preserve_order(s.region for s in signals)
    principals = _dedupe_preserve_order(
        s.principal for s in signals if _is_known_principal(s.principal)
    )

    region_label = ", ".join(regions) if regions else "multi-region"
    resource_label = resource_ids[0] if resource_ids else "account-wide scope"
    principal_label = principals[0] if principals else "an IAM principal"

    if breakdown.cloudtrail_count > 0 and (
        breakdown.metric_spike_count > 0 or breakdown.cost_delta_count > 0 or breakdown.iam_risk >= 60.0
    ):
        incident_type = "iam_compute_surge"
        title = f"Suspicious IAM activity correlated with compute/cost surge ({region_label})"
        summary = (
            f"Correlated {len(signals)} signals in {region_label} involving {principal_label} "
            f"and resource scope {', '.join(resource_ids) or 'account-level'}: "
            f"{breakdown.cloudtrail_count} CloudTrail event(s), "
            f"{breakdown.metric_spike_count} metric spike(s), and "
            f"+${breakdown.total_cost_delta_usd:.2f} billing delta."
        )
        actions = [
            f"Audit and temporarily restrict credentials/sessions for {principal_label}.",
            f"Inspect security group changes and recently launched compute in {region_label}.",
            f"Review resource {resource_label} for unauthorized workloads and terminate if unapproved.",
        ]
    elif has_traffic_spike and breakdown.cloudtrail_count == 0:
        incident_type = "bot_traffic_cost_spike"
        title = f"Automated traffic surge driving resource and cost spike on {resource_label}"
        summary = (
            f"Detected {breakdown.metric_spike_count} correlated traffic/utilization spike(s) "
            f"on {', '.join(resource_ids) or region_label} alongside "
            f"+${breakdown.total_cost_delta_usd:.2f} in unexpected spend."
        )
        actions = [
            "Enable AWS WAF rate-limiting rules on high-frequency endpoints.",
            "Block abusive client IPs/user-agents and enable CDN/edge caching.",
            f"Verify auto-scaling limits on {resource_label} to cap bot-induced cost.",
        ]
    elif breakdown.metric_spike_count > 0 and breakdown.cost_delta_count > 0:
        incident_type = "cost_utilization_anomaly"
        title = f"Sustained utilization spike increasing spend on {resource_label}"
        summary = (
            f"Correlated {breakdown.metric_spike_count} utilization spike(s) with "
            f"+${breakdown.total_cost_delta_usd:.2f} cost growth across "
            f"{', '.join(resource_ids) or region_label}."
        )
        actions = [
            f"Inspect workload saturation and recent deployments on {resource_label}.",
            "Set CloudWatch billing alarms and rightsize over-utilized compute tiers.",
        ]
    else:
        incident_type = "correlated_anomaly"
        title = f"Correlated multi-signal anomaly detected in {region_label}"
        summary = (
            f"Grouped {len(signals)} related telemetry signals within the correlation window "
            f"affecting {', '.join(resource_ids) or region_label}."
        )
        actions = [
            f"Inspect correlated event timeline for {resource_label}.",
            "Verify recent configuration changes and monitor resource telemetry.",
        ]

    return incident_type, title, summary, actions


def correlate_signals(
    cloudtrail_events: Iterable[CloudTrailEvent | dict[str, Any]] = (),
    metric_spikes: Iterable[MetricSpike | dict[str, Any]] = (),
    cost_deltas: Iterable[CostDelta | dict[str, Any]] = (),
    *,
    time_window_minutes: int = 60,
    min_signals: int = 2,
    require_multi_source: bool = False,
) -> list[CorrelatedIncident]:
    """Group related CloudTrail, metric spike, and cost delta signals within a time window."""
    if time_window_minutes <= 0:
        raise ValueError("time_window_minutes must be greater than 0")
    if min_signals < 1:
        raise ValueError("min_signals must be at least 1")

    max_gap = timedelta(minutes=time_window_minutes)
    signals = normalize_signals(cloudtrail_events, metric_spikes, cost_deltas)
    if not signals:
        return []

    clusters: list[_Cluster] = []

    for signal in signals:
        explicit_matches: list[tuple[int, _Cluster]] = []
        region_matches: list[_Cluster] = []

        for cluster in clusters:
            priority = cluster.match_priority(signal, max_gap)
            if priority in (1, 2):
                explicit_matches.append((priority, cluster))
            elif priority == 3:
                region_matches.append(cluster)

        if explicit_matches:
            # Sort so priority 1 (resource) comes first, and prefer most recent end timestamp.
            explicit_matches.sort(key=lambda item: (item[0], -item[1].end.timestamp()))
            target = explicit_matches[0][1]

            # Merge additional explicitly matched clusters if the combined time span fits max_gap.
            for _, candidate in explicit_matches[1:]:
                if candidate is target:
                    continue
                combined_start = min(target.start, candidate.start, signal.timestamp)
                combined_end = max(target.end, candidate.end, signal.timestamp)
                if (combined_end - combined_start) <= max_gap:
                    target.merge_from(candidate)
                    clusters.remove(candidate)

            target.add(signal)
        elif region_matches:
            # Never merge separate resource clusters on a region-only match; attach to the
            # closest/most-recent matching cluster in time.
            target = max(region_matches, key=lambda c: (c.end, len(c.signals)))
            target.add(signal)
        else:
            clusters.append(_Cluster(signal))

    incidents: list[CorrelatedIncident] = []
    for cluster in clusters:
        cluster_signals = sorted(
            cluster.signals, key=lambda sig: (sig.timestamp, sig.signal_type, sig.event_id)
        )
        if len(cluster_signals) < min_signals:
            continue
        if require_multi_source and len({s.signal_type for s in cluster_signals}) < 2:
            continue

        breakdown, risk_score, severity = _score_cluster(cluster_signals)
        incident_type, title, summary, actions = _classify_incident(cluster_signals, breakdown)
        resource_ids = _dedupe_preserve_order(rid for s in cluster_signals for rid in s.resource_ids)
        regions = _dedupe_preserve_order(s.region for s in cluster_signals)
        principals = _dedupe_preserve_order(
            s.principal for s in cluster_signals if _is_known_principal(s.principal)
        )

        incidents.append(
            CorrelatedIncident(
                incident_id="pending",
                incident_type=incident_type,
                title=title,
                severity=severity,
                risk_score=risk_score,
                primary_resource_id=resource_ids[0] if resource_ids else None,
                resource_ids=resource_ids,
                regions=regions,
                principals=principals,
                window_start=cluster_signals[0].timestamp,
                window_end=cluster_signals[-1].timestamp,
                correlated_event_ids=[s.event_id for s in cluster_signals],
                signal_breakdown=breakdown,
                signals=cluster_signals,
                summary=summary,
                recommended_actions=actions,
            )
        )

    incidents.sort(key=lambda inc: (-inc.risk_score, inc.window_start))
    for index, incident in enumerate(incidents, start=1):
        incident.incident_id = f"inc_{index:04d}"

    return incidents
