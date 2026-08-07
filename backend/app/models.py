from typing import Any

from pydantic import BaseModel, Field


class RepositoryCreate(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = None


class SearchRequest(BaseModel):
    repository_id: str
    query: str = Field(min_length=1)
    limit: int = Field(default=8, ge=1, le=20)


class ChatRequest(BaseModel):
    repository_id: str
    question: str = Field(min_length=1)
