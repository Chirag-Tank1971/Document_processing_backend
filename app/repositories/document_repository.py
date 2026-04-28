from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.document import Document, DocumentStatus, ProcessedResult, ProcessingJob


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_document(self, **kwargs) -> Document:
        document = Document(**kwargs)
        self.db.add(document)
        self.db.flush()
        return document

    def create_job(self, **kwargs) -> ProcessingJob:
        job = ProcessingJob(**kwargs)
        self.db.add(job)
        self.db.flush()
        return job

    def get_document(self, document_id: UUID) -> Document | None:
        stmt = select(Document).options(joinedload(Document.result)).where(Document.id == document_id)
        return self.db.scalar(stmt)

    def list_documents(
        self, search: str | None, status: DocumentStatus | None, sort_by: str, sort_order: str, offset: int, limit: int
    ) -> tuple[list[Document], int]:
        stmt = select(Document).options(joinedload(Document.result))
        count_stmt = select(func.count(Document.id))

        filters = []
        if search:
            filters.append(
                or_(Document.filename.ilike(f"%{search}%"), Document.content_type.ilike(f"%{search}%"))
            )
        if status:
            filters.append(Document.status == status)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        sort_col = Document.created_at if sort_by == "date" else Document.status
        if sort_order == "asc":
            stmt = stmt.order_by(sort_col.asc())
        else:
            stmt = stmt.order_by(sort_col.desc())

        items = list(self.db.scalars(stmt.offset(offset).limit(limit)))
        total = self.db.scalar(count_stmt) or 0
        return items, total

    def upsert_result(self, document: Document, payload: dict) -> ProcessedResult:
        result = document.result
        if result is None:
            result = ProcessedResult(document_id=document.id)
            self.db.add(result)

        result.title = payload.get("title")
        result.category = payload.get("category")
        result.summary = payload.get("summary")
        result.keywords = payload.get("keywords", [])
        result.raw_json = payload
        self.db.flush()
        return result
