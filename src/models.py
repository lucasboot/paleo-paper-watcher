from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Paper(BaseModel):
    source: str
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published_date: date | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    venue: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
