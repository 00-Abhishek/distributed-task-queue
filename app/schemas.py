"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    type: str = Field(..., min_length=1, max_length=100, examples=["echo"])
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(0, description="Higher values are claimed first")
    max_attempts: Optional[int] = Field(None, ge=1, le=20)
    delay_seconds: float = Field(0, ge=0, description="Delay before the job is runnable")


class JobOut(BaseModel):
    id: str
    type: str
    payload: dict[str, Any]
    status: str
    priority: int
    run_at: datetime
    attempts: int
    max_attempts: int
    last_error: Optional[str] = None
    result: Optional[Any] = None
    locked_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MetricsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    avg_processing_seconds: float
