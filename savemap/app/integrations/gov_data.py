import httpx

from app.core.config import settings


class GovDataClient:
    def __init__(self, base_url: str, service_key: str | None = None):
        self.base_url = base_url
        self.service_key = service_key or settings.data_go_kr_key

    async def fetch(self, path: str, params: dict) -> dict:
        if not self.service_key:
            raise RuntimeError("DATA_GO_KR_KEY 미설정")
        query = {"serviceKey": self.service_key, **params}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            resp = await client.get(path, params=query)
            resp.raise_for_status()
            return resp.json()
