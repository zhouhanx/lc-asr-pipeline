"""Tenant ASR model provider schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, SecretStr, model_validator

ModelKind = Literal["speech", "text", "ocr"]
ProviderType = Literal["local", "openai_compatible", "stepfun", "deepseek", "paddleocr"]


class ModelProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    model_kind: ModelKind
    provider_type: Literal["openai_compatible", "stepfun", "deepseek", "paddleocr"]
    base_url: HttpUrl
    model_name: str = Field(min_length=1, max_length=160)
    api_key: SecretStr = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_kind_and_provider(self) -> ModelProviderCreate:
        allowed = {
            "speech": {"openai_compatible", "stepfun"},
            "text": {"openai_compatible", "deepseek"},
            "ocr": {"paddleocr"},
        }
        if self.provider_type not in allowed[self.model_kind]:
            raise ValueError(f"{self.provider_type} is not valid for {self.model_kind} models")
        return self


class ModelProviderUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    base_url: HttpUrl
    model_name: str = Field(min_length=1, max_length=160)
    api_key: SecretStr | None = Field(default=None, max_length=4096)


class ModelProviderResponse(BaseModel):
    id: UUID
    name: str
    provider_type: ProviderType
    model_kind: ModelKind
    base_url: str
    model_name: str
    capabilities: list[str]
    is_enabled: bool
    is_default: bool
    is_system: bool
    has_api_key: bool
    created_at: datetime


class ModelProviderHealthResponse(BaseModel):
    id: UUID
    status: Literal["available", "unavailable", "misconfigured"]
    latency_ms: int | None = None
    detail: str
