from pydantic import BaseModel


class ReverseGeocodeResponse(BaseModel):
    region: str | None = None
