"""Versioned API router composition."""

from fastapi import APIRouter

from lc_asr_pipeline.api.routes import (
    admin,
    auth,
    health,
    jobs,
    models,
    ocr,
    resume_projects,
    tenants,
    uploads,
    workspace,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)
api_router.include_router(models.router)
api_router.include_router(uploads.router)
api_router.include_router(jobs.router)
api_router.include_router(ocr.router)
api_router.include_router(resume_projects.router)
api_router.include_router(workspace.router)
api_router.include_router(admin.router)
