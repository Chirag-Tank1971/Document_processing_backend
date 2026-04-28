import asyncio
import json
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.document import DocumentStatus
from app.schemas.document import (
    DocumentListResponse,
    DocumentResponse,
    FinalizeResponse,
    RetryResponse,
    UpdateResultRequest,
    UploadResponse,
)
from app.services.document_service import DocumentService

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
def upload_documents(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    service = DocumentService(db)
    ids = service.upload_documents(files)
    return UploadResponse(message="Documents queued successfully", document_ids=ids)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    search: str | None = None,
    status: DocumentStatus | None = None,
    sort_by: str = Query(default="date", pattern="^(date|status)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    service = DocumentService(db)
    items, total = service.repo.list_documents(search, status, sort_by, sort_order, offset, limit)
    return DocumentListResponse(items=items, total=total)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, db: Session = Depends(get_db)):
    service = DocumentService(db)
    return service.get_document_or_404(document_id)


@router.put("/documents/{document_id}", response_model=DocumentResponse)
def update_document(document_id: UUID, payload: UpdateResultRequest, db: Session = Depends(get_db)):
    service = DocumentService(db)
    return service.update_document_result(document_id, payload.model_dump())


@router.post("/retry/{document_id}", response_model=RetryResponse)
def retry_document(document_id: UUID, db: Session = Depends(get_db)):
    service = DocumentService(db)
    job = service.retry_document(document_id)
    return RetryResponse(message="Retry queued", job_id=job.id)


@router.post("/finalize/{document_id}", response_model=FinalizeResponse)
def finalize_document(document_id: UUID, db: Session = Depends(get_db)):
    service = DocumentService(db)
    service.finalize_document(document_id)
    return FinalizeResponse(message="Document finalized")


@router.get("/export/{document_id}")
def export_document(document_id: UUID, format: str = "json", db: Session = Depends(get_db)):
    service = DocumentService(db)
    return service.export_document(document_id, format)


@router.get("/progress/{document_id}")
async def stream_progress(document_id: UUID):
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"progress:{document_id}"
    pubsub.subscribe(channel)

    async def event_generator():
        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("data"):
                    data = json.loads(message["data"])
                    yield {"event": "progress", "data": json.dumps(data)}
                await asyncio.sleep(0.5)
        finally:
            pubsub.close()
            redis_client.close()

    return EventSourceResponse(event_generator())
