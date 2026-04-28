import json
from datetime import datetime, timezone
from uuid import UUID

import redis

from app.core.config import settings


class ProgressService:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def channel(document_id: UUID) -> str:
        return f"progress:{document_id}"

    def publish(
        self,
        document_id: UUID,
        job_id: UUID,
        step: str,
        progress: int,
        status: str,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        payload = {
            "document_id": str(document_id),
            "job_id": str(job_id),
            "step": step,
            "progress": progress,
            "status": status,
            "message": message,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.redis_client.publish(self.channel(document_id), json.dumps(payload))
