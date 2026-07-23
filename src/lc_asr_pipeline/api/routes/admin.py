"""Platform-wide administration endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from lc_asr_pipeline.api.admin_security import (
    CurrentPlatformAdmin,
    InitialPlatformAdmin,
)
from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.routes.jobs import (
    _validate_completed_transcript,
    _validate_export_format,
    build_job_export_response,
)
from lc_asr_pipeline.core.security import PasswordPolicyError
from lc_asr_pipeline.repositories.admin import AdminRepository
from lc_asr_pipeline.repositories.jobs import JobRepository
from lc_asr_pipeline.schemas.admin import (
    AdminJobDetail,
    AdminJobResponse,
    AdminProvisionedAccountResponse,
    AdminProvisionedUserResponse,
    AdminRecordingJobCreateRequest,
    AdminRecordingModelsResponse,
    AdminRecordingResponse,
    AdminResetUserPasswordResponse,
    AdminTenantCreateRequest,
    AdminTenantDeleteResponse,
    AdminTenantResponse,
    AdminTenantStatusUpdateRequest,
    AdminTenantUserCreateRequest,
    AdminUserResponse,
    AdminUserStatusUpdateRequest,
    PlatformAdminAuthResponse,
    PlatformAdminCurrentPasswordChangeRequest,
    PlatformAdminLoginRequest,
    PlatformAdminPasswordChangeRequest,
)
from lc_asr_pipeline.schemas.job import TranscriptionJobVisibilityUpdate
from lc_asr_pipeline.schemas.model_provider import ModelProviderResponse
from lc_asr_pipeline.services.admin import (
    AdminService,
    DuplicateProvisioningError,
    InvalidAdminCredentialsError,
    InvalidAdminCurrentPasswordError,
)

router = APIRouter(prefix="/admin", tags=["platform-administration"])
repository = AdminRepository()
job_repository = JobRepository()


@router.post("/auth/login", response_model=PlatformAdminAuthResponse)
async def admin_login(
    payload: PlatformAdminLoginRequest,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> PlatformAdminAuthResponse:
    try:
        result = await AdminService(database, settings).login(
            payload.username,
            payload.password,
        )
    except InvalidAdminCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials",
        ) from error
    return PlatformAdminAuthResponse(
        access_token=result.access_token,
        expires_at=result.expires_at,
        username=result.admin.username,
        password_change_required=result.admin.must_change_password,
    )


@router.post("/auth/change-initial-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_admin_initial_password(
    payload: PlatformAdminPasswordChangeRequest,
    admin: InitialPlatformAdmin,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> None:
    try:
        changed = await AdminService(database, settings).change_initial_password(
            admin.id,
            payload.new_password,
        )
    except PasswordPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=409, detail="Initial password was already changed")


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_admin_password(
    payload: PlatformAdminCurrentPasswordChangeRequest,
    admin: CurrentPlatformAdmin,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> None:
    try:
        changed = await AdminService(database, settings).change_password(
            admin,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidAdminCurrentPasswordError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except PasswordPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=409, detail="Password could not be changed")


@router.get("/tenants", response_model=list[AdminTenantResponse])
async def list_admin_tenants(
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> list[AdminTenantResponse]:
    async with database.connection() as connection:
        tenants = await repository.list_tenants(connection)
        users = await repository.list_users(connection)
    return _tenant_responses(tenants, users)


@router.post(
    "/tenants",
    response_model=AdminProvisionedAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_tenant(
    payload: AdminTenantCreateRequest,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> AdminProvisionedAccountResponse:
    try:
        created, initial_password = await AdminService(database, settings).create_tenant(
            tenant_name=payload.tenant_name,
            tenant_slug=payload.tenant_slug,
            owner_display_name=payload.owner_display_name,
            owner_email=str(payload.owner_email),
        )
    except DuplicateProvisioningError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    async with database.connection() as connection:
        tenants = await repository.list_tenants(connection)
        users = await repository.list_users(connection, created["tenant_id"])  # type: ignore[arg-type]
    tenant = next(item for item in tenants if item["id"] == created["tenant_id"])
    tenant_response = _tenant_responses([tenant], users)[0]
    user_response = next(
        user for user in tenant_response.users if user.id == created["user_id"]
    )
    return AdminProvisionedAccountResponse(
        tenant=tenant_response,
        user=user_response,
        initial_password=initial_password,
    )


@router.post(
    "/tenants/{tenant_id}/users",
    response_model=AdminProvisionedUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_user(
    tenant_id: UUID,
    payload: AdminTenantUserCreateRequest,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> AdminProvisionedUserResponse:
    try:
        user, initial_password = await AdminService(database, settings).create_user(
            tenant_id=tenant_id,
            email=str(payload.email),
            display_name=payload.display_name,
            role=payload.role,
        )
    except DuplicateProvisioningError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if user is None:
        raise HTTPException(status_code=404, detail="Active tenant not found")
    return AdminProvisionedUserResponse(
        user=AdminUserResponse.model_validate(user),
        initial_password=initial_password,
    )


@router.patch("/tenants/{tenant_id}", response_model=AdminTenantResponse)
async def update_admin_tenant(
    tenant_id: UUID,
    payload: AdminTenantStatusUpdateRequest,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminTenantResponse:
    async with database.connection() as connection:
        tenant = await repository.update_tenant_status(
            connection,
            tenant_id=tenant_id,
            tenant_status=payload.status,
        )
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        users = await repository.list_users(connection, tenant_id)
    return _tenant_responses([tenant], users)[0]


@router.delete("/tenants/{tenant_id}", response_model=AdminTenantDeleteResponse)
async def delete_admin_tenant(
    tenant_id: UUID,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminTenantDeleteResponse:
    async with database.connection() as connection:
        result = await repository.business_delete_tenant(
            connection,
            tenant_id=tenant_id,
        )
    if result is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if result["blocked"]:
        raise HTTPException(
            status_code=409,
            detail="Tenant has processing jobs; cancel or finish them before deletion",
        )
    return AdminTenantDeleteResponse(
        id=tenant_id,
        deleted_jobs=result["deleted_jobs"],
        retained_recordings=result["retained_recordings"],
        status="deleted",
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: UUID,
    payload: AdminUserStatusUpdateRequest,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminUserResponse:
    async with database.connection() as connection:
        user = await repository.update_user_status(
            connection,
            user_id=user_id,
            user_status=payload.status,
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminUserResponse.model_validate(user)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=AdminResetUserPasswordResponse,
)
async def reset_admin_user_password(
    user_id: UUID,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> AdminResetUserPasswordResponse:
    user, initial_password = await AdminService(database, settings).reset_user_password(
        user_id=user_id,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return AdminResetUserPasswordResponse(
        user=AdminUserResponse.model_validate(user),
        initial_password=initial_password,
    )


@router.get("/jobs", response_model=list[AdminJobResponse])
async def list_admin_jobs(
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
    tenant_id: UUID | None = None,
) -> list[AdminJobResponse]:
    async with database.connection() as connection:
        jobs = await repository.list_jobs(connection, tenant_id)
    return [AdminJobResponse.model_validate(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=AdminJobDetail)
async def get_admin_job(
    job_id: UUID,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminJobDetail:
    async with database.connection() as connection:
        job = await repository.get_job(connection, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        segments = await repository.job_segments(connection, job_id)
    return AdminJobDetail.model_validate({**job, "segments": segments})


@router.patch("/jobs/{job_id}/visibility", response_model=AdminJobResponse)
async def update_admin_job_visibility(
    job_id: UUID,
    payload: TranscriptionJobVisibilityUpdate,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminJobResponse:
    async with database.connection() as connection:
        job = await repository.update_job_visibility(
            connection,
            job_id=job_id,
            visibility=payload.visibility,
        )
    if job is None:
        raise HTTPException(status_code=404, detail="Transcription job not found")
    return AdminJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/retry", response_model=AdminJobResponse)
async def retry_admin_job(
    job_id: UUID,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminJobResponse:
    async with database.connection() as connection:
        current = await repository.get_job(connection, job_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        retried = await job_repository.retry(
            connection,
            tenant_id=UUID(str(current["tenant_id"])),
            job_id=job_id,
        )
        job = await repository.get_job(connection, job_id) if retried is not None else None
    if job is None:
        raise HTTPException(status_code=409, detail="Job cannot be retried")
    return AdminJobResponse.model_validate(job)


@router.get("/jobs/{job_id}/export/{export_format}")
async def export_admin_job(
    job_id: UUID,
    export_format: str,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> Response:
    _validate_export_format(export_format)
    async with database.connection() as connection:
        job = await repository.get_job(connection, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        _validate_completed_transcript(job)
        segments = await repository.job_segments(connection, job_id)
    detail = AdminJobDetail.model_validate({**job, "segments": segments})
    return build_job_export_response(
        job_id=job_id,
        export_format=export_format,
        row=job,
        segments=segments,
        json_payload=detail.model_dump_json(indent=2),
    )


@router.get("/recordings", response_model=list[AdminRecordingResponse])
async def list_admin_recordings(
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> list[AdminRecordingResponse]:
    async with database.connection() as connection:
        recordings = await repository.list_recordings(connection)
    return [AdminRecordingResponse.model_validate(item) for item in recordings]


@router.get(
    "/recordings/{recording_id}/models",
    response_model=AdminRecordingModelsResponse,
)
async def list_admin_recording_models(
    recording_id: UUID,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminRecordingModelsResponse:
    async with database.connection() as connection:
        recording = await repository.get_recording(connection, recording_id)
        if recording is None:
            raise HTTPException(status_code=404, detail="Recording not found")
        models = await repository.list_recording_models(
            connection,
            recording_id=recording_id,
        )
    return AdminRecordingModelsResponse(
        recording=AdminRecordingResponse.model_validate(recording),
        models=[ModelProviderResponse.model_validate(model) for model in models],
    )


@router.post(
    "/recordings/{recording_id}/jobs",
    response_model=AdminJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_recording_job(
    recording_id: UUID,
    payload: AdminRecordingJobCreateRequest,
    _: CurrentPlatformAdmin,
    database: DatabaseDependency,
) -> AdminJobResponse:
    async with database.connection() as connection:
        context = await repository.recording_job_context(
            connection,
            recording_id=recording_id,
        )
        if context is None:
            raise HTTPException(
                status_code=409,
                detail="Recording has no tenant account for task attribution",
            )
        tenant_id, user_id = context
        jobs = await job_repository.create_many(
            connection,
            tenant_id=tenant_id,
            user_id=user_id,
            provider_id=payload.provider_id,
            text_provider_id=payload.text_provider_id,
            file_ids=[recording_id],
            language=payload.language,
            diarize=payload.diarize,
            speaker_mode=payload.speaker_mode,
        )
        if len(jobs) != 1:
            raise HTTPException(
                status_code=409,
                detail="Provider unavailable, file not ready, or task cannot be created",
            )
        job = await repository.get_job(connection, jobs[0]["id"])
    if job is None:
        raise HTTPException(status_code=409, detail="Task could not be loaded")
    return AdminJobResponse.model_validate(job)


def _tenant_responses(
    tenants: list[dict[str, object]],
    users: list[dict[str, object]],
) -> list[AdminTenantResponse]:
    return [
        AdminTenantResponse.model_validate(
            {
                **tenant,
                "users": [user for user in users if user["tenant_id"] == tenant["id"]],
            }
        )
        for tenant in tenants
    ]
