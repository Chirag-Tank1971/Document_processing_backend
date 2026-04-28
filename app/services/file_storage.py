from celery import uuid as celery_uuid

from app.core.config import settings


class FileStorageService:
    def __init__(self):
        if not self.use_supabase:
            raise RuntimeError(
                "Supabase storage is required. Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and "
                "SUPABASE_STORAGE_BUCKET."
            )
        try:
            from supabase import create_client
        except Exception as exc:
            raise RuntimeError(
                "Supabase storage is required but 'supabase' client failed to import. "
                "Install a compatible supabase package in this environment."
            ) from exc
        self._supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    @property
    def use_supabase(self) -> bool:
        return bool(settings.supabase_url and settings.supabase_service_role_key and settings.supabase_storage_bucket)

    def save_upload(self, filename: str, content: bytes, content_type: str) -> str:
        safe_name = filename.replace("/", "_").replace("\\", "_")
        object_key = f"uploads/{celery_uuid()}_{safe_name}"

        self._supabase_client.storage.from_(settings.supabase_storage_bucket).upload(
            object_key,
            content,
            {"content-type": content_type, "upsert": "false"},
        )
        return f"supabase://{settings.supabase_storage_bucket}/{object_key}"

    def read_text(self, file_ref: str) -> str:
        if not file_ref.startswith("supabase://"):
            raise RuntimeError("Invalid file reference. Expected Supabase storage reference.")
        bucket_and_key = file_ref.removeprefix("supabase://")
        bucket, object_key = bucket_and_key.split("/", 1)
        content = self._supabase_client.storage.from_(bucket).download(object_key)
        return content.decode("utf-8", errors="ignore")
