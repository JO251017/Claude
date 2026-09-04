import httpx

from app.core.config import settings
from app.core.errors import ImageUploadError


class SupabaseStorageClient:
    def __init__(self):
        self.url = settings.supabase_url
        self.key = settings.supabase_service_key
        self.bucket = settings.supabase_storage_bucket

    async def upload(self, path: str, content: bytes, content_type: str) -> str:
        if not self.url or not self.key:
            raise ImageUploadError("사진 저장소가 설정되지 않았습니다 (SUPABASE_SERVICE_KEY 미설정)")
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(endpoint, content=content, headers=headers)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageUploadError(f"사진 업로드에 실패했습니다: {exc.__class__.__name__}") from exc
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"
