from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.knowledge import (HitOut, KnowledgeCreate, KnowledgeDocumentDetail, KnowledgeDocumentOut,
                                   KnowledgeStatsOut, ReindexOut)
from app.services import knowledge_service

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def read_upload(file: UploadFile) -> bytes:
    """Read an upload, but never more than the limit (plus one byte, so we can tell it was too big)."""
    return file.file.read(get_settings().knowledge_max_upload_mb * 1024 * 1024 + 1)


@router.get("/status", response_model=KnowledgeStatsOut)
def knowledge_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return knowledge_service.stats(db)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return knowledge_service.list_documents(db)


@router.post("/documents", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
def add_document(data: KnowledgeCreate, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    return knowledge_service.add_document(db, user, data.title, data.text, data.category, request=request)


@router.post("/documents/upload", response_model=KnowledgeDocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(request: Request, file: UploadFile = File(...), title: str = Form(""), category: str = Form("other"),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return knowledge_service.add_uploaded_file(db, user, file.filename or "", read_upload(file), title, category, request)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentDetail)
def get_document(document_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    document = knowledge_service.get_document(db, document_id)
    return {**KnowledgeDocumentOut.model_validate(document).model_dump(),
            "chunks": [{"position": c.position, "text": c.text, "has_embedding": c.embedding is not None}
                       for c in document.chunks]}


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    knowledge_service.delete_document(db, user, document_id, request)
    return {"deleted": document_id}


@router.get("/search", response_model=list[HitOut])
def search(q: str, limit: int = 4, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [hit.__dict__ for hit in knowledge_service.search(db, q, limit)]


@router.post("/reindex", response_model=ReindexOut)
def reindex(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return knowledge_service.reindex(db, user, request)
