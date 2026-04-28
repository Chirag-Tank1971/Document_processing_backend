from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import DocumentStatus


class ProcessedResultResponse(BaseModel):
    title: str | None = None
    category: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    raw_json: dict | None = None

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    is_finalized: bool
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    result: ProcessedResultResponse | None = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class UpdateResultRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    summary: str | None = None
    keywords: list[str] = Field(default_factory=list)


class UploadResponse(BaseModel):
    message: str
    document_ids: list[UUID]


class RetryResponse(BaseModel):
    message: str
    job_id: UUID


class FinalizeResponse(BaseModel):
    message: str
