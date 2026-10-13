from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "other"
    text: str = Field(min_length=1)


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    filename: str | None
    source: str
    char_count: int
    chunk_count: int
    created_at: datetime


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    text: str
    has_embedding: bool = False


class KnowledgeDocumentDetail(KnowledgeDocumentOut):
    chunks: list[ChunkOut]


class HitOut(BaseModel):
    chunk_id: int
    document_id: int
    title: str
    text: str
    score: float
    via: str


class KnowledgeStatsOut(BaseModel):
    documents: int
    passages: int
    embedded_passages: int
    semantic_enabled: bool
    embedding_model: str
    capacity: int


class ReindexOut(BaseModel):
    embedded: int
    remaining: int
