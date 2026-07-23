"""Workspace dashboard response contracts."""

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    running_tasks: int = Field(ge=0)
    queued_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    available_models: int = Field(ge=0)
    historical_files: int = Field(ge=0)
