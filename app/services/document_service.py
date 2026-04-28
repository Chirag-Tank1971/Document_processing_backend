import csv
import io
import json
from uuid import UUID

from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.file_storage import FileStorageService
from app.workers.tasks import process_document_task


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)
        self.file_storage = FileStorageService()

    def upload_documents(self, files: list[UploadFile]) -> list[UUID]:
        if not files:
            raise HTTPException(status_code=400, detail="No files were uploaded")
        if len(files) > settings.max_files_per_upload:
            raise HTTPException(
                status_code=400,
                detail=f"You can upload up to {settings.max_files_per_upload} files at a time",
            )

        created_document_ids: list[UUID] = []
        for file in files:
            contents = file.file.read()
            max_size_bytes = settings.max_file_size_mb * 1024 * 1024
            if len(contents) > max_size_bytes:
                raise HTTPException(status_code=400, detail=f"{file.filename} exceeds max size limit")

            file_ref = self.file_storage.save_upload(
                filename=file.filename,
                content=contents,
                content_type=file.content_type or "application/octet-stream",
            )

            document = self.repo.create_document(
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=len(contents),
                status=DocumentStatus.queued,
                file_path=file_ref,
            )
            job = self.repo.create_job(document_id=document.id, status=DocumentStatus.queued, attempt=1)
            self.db.commit()

            async_result = process_document_task.delay(str(document.id), str(job.id))
            job.celery_task_id = async_result.id
            self.db.commit()
            created_document_ids.append(document.id)

        return created_document_ids

    def get_document_or_404(self, document_id: UUID) -> Document:
        document = self.repo.get_document(document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    def update_document_result(self, document_id: UUID, payload: dict) -> Document:
        document = self.get_document_or_404(document_id)
        if document.is_finalized:
            raise HTTPException(status_code=400, detail="Document is finalized and cannot be edited")
        self.repo.upsert_result(document, payload)
        self.db.commit()
        self.db.refresh(document)
        return document

    def finalize_document(self, document_id: UUID) -> Document:
        document = self.get_document_or_404(document_id)
        if document.status != DocumentStatus.completed:
            raise HTTPException(status_code=400, detail="Only completed documents can be finalized")
        document.is_finalized = True
        self.db.commit()
        self.db.refresh(document)
        return document

    def retry_document(self, document_id: UUID):
        document = self.get_document_or_404(document_id)
        if document.status != DocumentStatus.failed:
            raise HTTPException(status_code=400, detail="Retry allowed only for failed documents")

        attempts = len(document.jobs) + 1
        document.status = DocumentStatus.queued
        document.error_message = None
        job = self.repo.create_job(document_id=document.id, status=DocumentStatus.queued, attempt=attempts)
        self.db.commit()

        async_result = process_document_task.delay(str(document.id), str(job.id))
        job.celery_task_id = async_result.id
        self.db.commit()
        return job

    def export_document(self, document_id: UUID, output_format: str) -> StreamingResponse:
        document = self.get_document_or_404(document_id)
        if not document.is_finalized or not document.result:
            raise HTTPException(status_code=400, detail="Document must be finalized before export")

        payload = {
            "id": str(document.id),
            "filename": document.filename,
            "title": document.result.title,
            "category": document.result.category,
            "summary": document.result.summary,
            "keywords": document.result.keywords or [],
        }

        if output_format == "json":
            body = json.dumps(payload, indent=2)
            return StreamingResponse(
                io.BytesIO(body.encode("utf-8")),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{document.id}.json"'},
            )

        if output_format == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(payload.keys()))
            writer.writeheader()
            writer.writerow(
                {
                    **payload,
                    "keywords": ",".join(payload["keywords"]),
                }
            )
            return StreamingResponse(
                io.BytesIO(buffer.getvalue().encode("utf-8")),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{document.id}.csv"'},
            )

        raise HTTPException(status_code=400, detail="format must be json or csv")
