import httpx

from app.core.config import settings


class SupabaseStorageClient:
    def __init__(self):
        self.url = settings.supabase_url
        self.key = settings.supabase_service_key
        self.bucket = settings.supabase_storage_bucket

    async def upload(self, path: str, content: bytes, content_type: str) -> str:
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY 미설정")
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": content_type}
        async with httpx.AsyncClient() as client:
            resp = await client.post(endpoint, content=content, headers=headers)
            resp.raise_for_status()
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"
