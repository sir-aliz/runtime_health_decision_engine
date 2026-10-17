"""Input contracts. Metric timestamps mark the end of non-overlapping buckets."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Timestamped(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    service_id: str = Field(min_length=1, max_length=120)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("Use a timezone-aware ISO timestamp or Unix seconds")
        value = value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc):
            raise ValueError("Future timestamps are not accepted")
        return value


class MetricData(Timestamped):
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    error_count: int = Field(ge=0, strict=True)
    request_count: int = Field(ge=0, strict=True)
    interval_seconds: int = Field(default=60, ge=1, le=600, strict=True)

    @model_validator(mode="after")
    def consistent_counts(self):
        if self.error_count > self.request_count:
            raise ValueError("error_count cannot exceed request_count")
        return self


class DeploymentData(Timestamped):
    version: str = Field(min_length=1, max_length=120)
    previous_version: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def changed_version(self):
        if self.version == self.previous_version:
            raise ValueError("version must differ from previous_version")
        return self
