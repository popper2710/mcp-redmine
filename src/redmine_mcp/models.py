"""Pydantic models for Redmine API responses and requests."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class RedmineError(Exception):
    """Base exception for Redmine API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class RedmineConfig(BaseModel):
    """Configuration for Redmine API client."""

    url: str = Field(..., description="Redmine instance URL")
    api_key: str = Field(..., description="Redmine API key")
    timeout: int = Field(default=30, description="Request timeout in seconds")

    class Config:
        frozen = True
