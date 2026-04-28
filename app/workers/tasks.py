import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.document import Document, DocumentStatus, ProcessingJob
from app.services.file_storage import FileStorageService
from app.services.progress_service import ProgressService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
progress_service = ProgressService()
file_storage_service = FileStorageService()


def _publish(
    document_id: UUID,
    job_id: UUID,
    step: str,
    progress: int,
    status: str,
    message: str | None = None,
    error: str | None = None,
):
    progress_service.publish(
        document_id=document_id,
        job_id=job_id,
        step=step,
        progress=progress,
        status=status,
        message=message,
        error=error,
    )


@celery_app.task(name="process_document_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_document_task(self, document_id: str, job_id: str):
    db = SessionLocal()
    doc_uuid = UUID(document_id)
    job_uuid = UUID(job_id)

    try:
        document = db.scalar(select(Document).where(Document.id == doc_uuid))
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_uuid))
        if not document or not job:
            return

        document.status = DocumentStatus.processing
        job.status = DocumentStatus.processing
        db.commit()

        _publish(doc_uuid, job_uuid, "document_received", 5, "processing", "Document accepted")
        time.sleep(1)

        _publish(doc_uuid, job_uuid, "parsing_started", 20, "processing", "Parsing started")
        time.sleep(1)

        file_text = file_storage_service.read_text(document.file_path)
        parsed_text = file_text[:2000] if file_text else f"Parsed content for {document.filename}"
        _publish(doc_uuid, job_uuid, "parsing_completed", 45, "processing", "Parsing completed")
        time.sleep(1)

        _publish(doc_uuid, job_uuid, "extraction_started", 60, "processing", "Extraction started")
        time.sleep(1)

        keywords = [token.strip(".,") for token in parsed_text.split()[:8]]
        payload = {
            "title": document.filename.rsplit(".", 1)[0][:120],
            "category": document.content_type.split("/")[0].upper(),
            "summary": (parsed_text[:280] + "...") if len(parsed_text) > 280 else parsed_text,
            "keywords": [k for k in keywords if k],
            "source": {
                "filename": document.filename,
                "file_type": document.content_type,
                "size_bytes": document.size_bytes,
            },
        }
        _publish(doc_uuid, job_uuid, "extraction_completed", 80, "processing", "Extraction completed")

        if document.result is None:
            from app.models.document import ProcessedResult

            document.result = ProcessedResult(document_id=document.id)

        document.result.title = payload["title"]
        document.result.category = payload["category"]
        document.result.summary = payload["summary"]
        document.result.keywords = payload["keywords"]
        document.result.raw_json = payload
        _publish(doc_uuid, job_uuid, "final_result_stored", 95, "processing", "Final result persisted")

        document.status = DocumentStatus.completed
        document.error_message = None
        job.status = DocumentStatus.completed
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        _publish(doc_uuid, job_uuid, "job_completed", 100, "completed", "Job completed")
    except Exception as exc:
        logger.exception("Document processing failed")
        will_retry = self.request.retries < self.max_retries
        document = db.scalar(select(Document).where(Document.id == doc_uuid))
        job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_uuid))
        if document:
            document.status = DocumentStatus.queued if will_retry else DocumentStatus.failed
            document.error_message = str(exc)
        if job:
            job.status = DocumentStatus.queued if will_retry else DocumentStatus.failed
            job.error_message = str(exc)
            job.completed_at = None if will_retry else datetime.now(timezone.utc)
        db.commit()
        # Never let error reporting mask the root exception.
        try:
            if will_retry:
                _publish(
                    doc_uuid,
                    job_uuid,
                    "retry_scheduled",
                    10,
                    "queued",
                    message="Temporary failure, retrying",
                    error=str(exc),
                )
            else:
                _publish(doc_uuid, job_uuid, "failed", 100, "failed", message="Processing failed", error=str(exc))
        except Exception:
            logger.exception("Failed to publish failure event")
        raise
    finally:
        db.close()
