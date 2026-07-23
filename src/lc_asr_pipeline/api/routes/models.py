"""Tenant model provider API."""

import time
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Security, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.model_providers import ModelProviderRepository
from lc_asr_pipeline.schemas.model_provider import (
    ModelProviderCreate,
    ModelProviderHealthResponse,
    ModelProviderResponse,
    ModelProviderUpdate,
)
from lc_asr_pipeline.services.model_secrets import (
    ModelSecretError,
    decrypt_model_secret,
    encrypt_model_secret,
)
from lc_asr_pipeline.services.network_policy import (
    UnsafeProviderURL,
    enforce_provider_network_policy,
    validate_provider_url,
)
from lc_asr_pipeline.services.secrets import resolve_secret_reference

router = APIRouter(prefix="/models", tags=["models"])
repository = ModelProviderRepository()

ModelReader = Annotated[Account, Security(get_current_account, scopes=["models:read"])]
ModelWriter = Annotated[Account, Security(get_current_account, scopes=["models:write"])]


@router.get("", response_model=list[ModelProviderResponse])
async def list_models(
    account: ModelReader,
    database: DatabaseDependency,
) -> list[ModelProviderResponse]:
    async with database.connection() as connection:
        rows = await repository.list_for_tenant(connection, account.tenant_id)
    return [ModelProviderResponse.model_validate(row) for row in rows]


@router.post("", response_model=ModelProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_model(
    payload: ModelProviderCreate,
    account: ModelWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> ModelProviderResponse:
    try:
        validate_provider_url(str(payload.base_url))
    except UnsafeProviderURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with database.connection() as connection:
        row = await repository.create(
            connection,
            tenant_id=account.tenant_id,
            name=payload.name,
            model_kind=payload.model_kind,
            provider_type=payload.provider_type,
            base_url=str(payload.base_url).rstrip("/"),
            model_name=payload.model_name,
            api_key_ciphertext=encrypt_model_secret(
                payload.api_key.get_secret_value(),
                master_secret=settings.model_secret_key,
                tenant_id=account.tenant_id,
            ),
            capabilities=(
                ["transcription", "timestamps"]
                if payload.model_kind == "speech"
                else ["ocr", "document_parsing", "markdown", "image", "pdf"]
                if payload.model_kind == "ocr"
                else ["chat", "transcript_refinement", "json_output"]
            ),
        )
    return ModelProviderResponse.model_validate(row)


@router.put("/{provider_id}", response_model=ModelProviderResponse)
async def update_model(
    provider_id: UUID,
    payload: ModelProviderUpdate,
    account: ModelWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> ModelProviderResponse:
    try:
        validate_provider_url(str(payload.base_url))
    except UnsafeProviderURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    encrypted = (
        encrypt_model_secret(
            payload.api_key.get_secret_value(),
            master_secret=settings.model_secret_key,
            tenant_id=account.tenant_id,
        )
        if payload.api_key is not None and payload.api_key.get_secret_value()
        else None
    )
    async with database.connection() as connection:
        row = await repository.update(
            connection,
            tenant_id=account.tenant_id,
            provider_id=provider_id,
            name=payload.name,
            base_url=str(payload.base_url).rstrip("/"),
            model_name=payload.model_name,
            api_key_ciphertext=encrypted,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Editable model provider not found")
    return ModelProviderResponse.model_validate(row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
    provider_id: UUID,
    account: ModelWriter,
    database: DatabaseDependency,
) -> None:
    async with database.connection() as connection:
        result = await repository.delete(
            connection,
            tenant_id=account.tenant_id,
            provider_id=provider_id,
        )
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Model provider not found")


@router.post("/{provider_id}/test", response_model=ModelProviderHealthResponse)
async def test_model(
    provider_id: UUID,
    account: ModelWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> ModelProviderHealthResponse:
    async with database.connection() as connection:
        provider = await repository.get_for_tenant(
            connection,
            tenant_id=account.tenant_id,
            provider_id=provider_id,
        )
    if provider is None:
        raise HTTPException(status_code=404, detail="Model provider not found")
    try:
        api_key = (
            decrypt_model_secret(
                provider["api_key_ciphertext"],
                master_secret=settings.model_secret_key,
                tenant_id=account.tenant_id,
            )
            if provider["api_key_ciphertext"] is not None
            else resolve_secret_reference(
                str(provider["api_key_env"]) if provider["api_key_env"] else None
            )
        )
    except ModelSecretError:
        api_key = None
    if not api_key:
        return ModelProviderHealthResponse(
            id=provider_id,
            status="misconfigured",
            detail="Referenced API key is not configured",
        )
    base_url = str(provider["base_url"]).rstrip("/")
    is_paddleocr = provider["provider_type"] == "paddleocr"
    models_url = (
        f"{base_url}/__connection_test__"
        if is_paddleocr and base_url.endswith("/jobs")
        else f"{base_url}/jobs/__connection_test__"
        if is_paddleocr
        else base_url + ("/models" if base_url.endswith("/v1") else "/v1/models")
    )
    started = time.monotonic()
    try:
        await enforce_provider_network_policy(
            base_url,
            allow_private=provider["provider_type"] == "local",
            trusted_hosts=(
                {"api.stepfun.com"}
                if provider["provider_type"] == "stepfun"
                else {"api.deepseek.com"}
                if provider["provider_type"] == "deepseek"
                else {"paddleocr.aistudio-app.com"}
                if is_paddleocr
                else ()
            ),
        )
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if is_paddleocr:
            if response.status_code in {401, 403} or response.status_code >= 500:
                response.raise_for_status()
        else:
            response.raise_for_status()
    except (httpx.HTTPError, OSError, UnsafeProviderURL):
        return ModelProviderHealthResponse(
            id=provider_id,
            status="unavailable",
            latency_ms=round((time.monotonic() - started) * 1000),
            detail="Provider health check failed",
        )
    return ModelProviderHealthResponse(
        id=provider_id,
        status="available",
        latency_ms=round((time.monotonic() - started) * 1000),
        detail=(
            "PaddleOCR API authentication endpoint is reachable"
            if is_paddleocr
            else "Provider model discovery succeeded"
        ),
    )


@router.post("/{provider_id}/default", response_model=ModelProviderResponse)
async def set_default_model(
    provider_id: UUID,
    account: ModelWriter,
    database: DatabaseDependency,
) -> ModelProviderResponse:
    async with database.connection() as connection:
        provider = await repository.set_default(
            connection,
            tenant_id=account.tenant_id,
            provider_id=provider_id,
        )
    if provider is None:
        raise HTTPException(status_code=404, detail="Model provider not found")
    return ModelProviderResponse.model_validate(provider)
