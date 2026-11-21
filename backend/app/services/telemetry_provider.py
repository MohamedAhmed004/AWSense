"""Telemetry provider interface, AWS boto3 stub, and provider factory."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

import boto3


class TelemetryProvider(ABC):
    """Abstract data-ingestion interface decoupling analysis from AWS/mock sources."""

    source_name: str = "base"

    @abstractmethod
    def get_resources(self) -> list[dict[str, Any]]:
        """Return inventory records for monitored AWS resources (EC2, EBS, RDS, S3)."""

    @abstractmethod
    def get_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return time-series CloudWatch utilization and request metrics."""

    @abstractmethod
    def get_cloudtrail_events(self) -> list[dict[str, Any]]:
        """Return normalized CloudTrail API and IAM audit events."""

    @abstractmethod
    def get_traffic_logs(self) -> list[dict[str, Any]]:
        """Return application/network traffic telemetry and bot-indicator records."""

    @abstractmethod
    def get_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        """Return Cost Explorer daily service spend and cost anomaly records."""


class Boto3TelemetryProvider(TelemetryProvider):
    """AWS SDK telemetry provider stub until live AWS sandbox credentials are active."""

    source_name: str = "aws"

    def __init__(
        self,
        region_name: str | None = None,
        profile_name: str | None = None,
    ) -> None:
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.profile_name = profile_name or os.getenv("AWS_PROFILE")
        self._session: boto3.Session | None = None

    def get_session(self) -> boto3.Session:
        """Lazily create a boto3 session configured for the target region/profile."""
        if self._session is None:
            session_kwargs: dict[str, str] = {"region_name": self.region_name}
            if self.profile_name:
                session_kwargs["profile_name"] = self.profile_name
            self._session = boto3.Session(**session_kwargs)
        return self._session

    def _not_configured(self, capability: str) -> NotImplementedError:
        return NotImplementedError(
            f"Boto3TelemetryProvider.{capability}() is not implemented yet. "
            "Set DATA_SOURCE=mock for synthetic telemetry or implement live boto3 collectors."
        )

    def get_resources(self) -> list[dict[str, Any]]:
        raise self._not_configured("get_resources")

    def get_metrics(
        self,
        resource_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        raise self._not_configured("get_metrics")

    def get_cloudtrail_events(self) -> list[dict[str, Any]]:
        raise self._not_configured("get_cloudtrail_events")

    def get_traffic_logs(self) -> list[dict[str, Any]]:
        raise self._not_configured("get_traffic_logs")

    def get_cost_usage(self, days: int = 30) -> list[dict[str, Any]]:
        raise self._not_configured("get_cost_usage")


def get_telemetry_provider(source: str | None = None) -> TelemetryProvider:
    """Instantiate the configured telemetry provider ('mock' or 'aws')."""
    selected = (source or os.getenv("DATA_SOURCE", "mock")).strip().lower()
    if selected == "mock":
        from app.services.mock_generator import MockTelemetryProvider

        return MockTelemetryProvider()
    if selected == "aws":
        return Boto3TelemetryProvider()
    raise ValueError(f"Unsupported DATA_SOURCE '{selected}'. Expected 'mock' or 'aws'.")
