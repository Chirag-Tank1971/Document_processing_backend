from pathlib import Path

from celery import uuid as celery_uuid
from supabase import Client, create_client

from app.core.config import settings


class FileStorageService:
    def __init__(self):
        self.uploads_dir = Path(settings.uploads_dir)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

        self._supabase_client: Client | None = None
        if self.use_supabase:
            self._supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    @property
    def use_supabase(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key and settings.supabase_storage_bucket)

    def save_upload(self, filename: str, content: bytes, content_type: str) -> str:
        safe_name = filename.replace("/", "_").replace("\\", "_")
        object_key = f"uploads/{celery_uuid()}_{safe_name}"

        if self.use_supabase:
            assert self._supabase_client is not None
            self._supabase_client.storage.from_(settings.supabase_storage_bucket).upload(
                object_key,
                content,
                {"content-type": content_type, "upsert": "false"},
            )
            return f"supabase://{settings.supabase_storage_bucket}/{object_key}"

        storage_path = self.uploads_dir / f"{celery_uuid()}_{safe_name}"
        with storage_path.open("wb") as out:
            out.write(content)
        return str(storage_path)

    def read_text(self, file_ref: str) -> str:
        if file_ref.startswith("supabase://"):
            bucket_and_key = file_ref.removeprefix("supabase://")
            bucket, object_key = bucket_and_key.split("/", 1)
            assert self._supabase_client is not None
            content = self._supabase_client.storage.from_(bucket).download(object_key)
            return content.decode("utf-8", errors="ignore")

        return Path(file_ref).read_text(encoding="utf-8", errors="ignore")
