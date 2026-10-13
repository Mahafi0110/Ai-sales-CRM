"""Company knowledge: add documents, search them, and hand relevant passages to the AI.

Everyone can search; only managers and admins can add, delete or re-index documents.
Searching never fails because of a problem with the embedding service: it falls back to keyword search.
"""
import logging

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.embeddings import embedding_tag, get_embeddings
from app.core.config import get_settings
from app.knowledge import extract
from app.knowledge.search import Candidate, Hit, bm25_rank, encode_vector, fuse, semantic_rank
from app.knowledge.text import clean_text, split_text
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import User
from app.services import access, audit_service

log = logging.getLogger(__name__)
CATEGORIES = ["playbook", "pricing", "product", "case_study", "policy", "other"]


# ---------- embeddings (always best-effort) ----------
def _embed_texts(texts: list[str]) -> list[bytes | None]:
    """Vectors for each text, as stored bytes; None where embedding was not possible (no key, quota, network).
    After the first failed batch we stop, so a usage limit is not hammered."""
    results: list[bytes | None] = [None] * len(texts)
    embeddings = get_embeddings()
    if embeddings is None or not texts:
        return results
    size = get_settings().embedding_batch_size
    for start in range(0, len(texts), size):
        batch = texts[start:start + size]
        try:
            vectors = embeddings.embed_documents(batch)
        except Exception:
            log.warning("Embedding failed; the rest will use keyword search until you re-index", exc_info=True)
            break
        for offset, vector in enumerate(vectors):
            results[start + offset] = encode_vector(vector)
    return results


# ---------- adding documents ----------
def add_document(db: Session, user: User, title: str, text: str, category: str = "other",
                 filename: str | None = None, source: str = "text", request: Request | None = None) -> KnowledgeDocument:
    access.ensure_manager(user)
    settings = get_settings()
    title = (title or "").strip()
    if not title or len(title) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the document a title (up to 200 characters).")
    if category not in CATEGORIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Category must be one of: {', '.join(CATEGORIES)}")
    text = clean_text(text or "")
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The document is empty.")
    if len(text) > settings.knowledge_max_chars:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"This document is too long (the limit is {settings.knowledge_max_chars:,} characters). "
                            "Split it into smaller documents.")
    chunks = split_text(text)
    used = db.scalar(select(func.count(KnowledgeChunk.id))) or 0
    if used + len(chunks) > settings.knowledge_max_passages:
        # Refuse loudly instead of letting new documents quietly fall outside the search.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"The knowledge library is full ({used:,} of {settings.knowledge_max_passages:,} passages, "
                            f"and this document needs {len(chunks):,}). Delete documents you no longer need first.")
    vectors = _embed_texts(chunks)
    tag = embedding_tag()
    document = KnowledgeDocument(title=title, category=category, filename=filename, source=source,
                                 char_count=len(text), chunk_count=len(chunks), uploaded_by_id=user.id)
    document.chunks = [KnowledgeChunk(position=i, text=chunk, embedding=vec, embedding_model=tag if vec else None)
                       for i, (chunk, vec) in enumerate(zip(chunks, vectors))]
    db.add(document)
    db.commit()
    db.refresh(document)
    audit_service.log_action(db, "knowledge_added", user.id, "knowledge_document", document.id,
                             {"title": title, "chunks": len(chunks), "embedded": sum(v is not None for v in vectors),
                              "source": source}, request)
    return document


def add_uploaded_file(db: Session, user: User, filename: str, data: bytes, title: str | None, category: str,
                      request: Request | None = None) -> KnowledgeDocument:
    access.ensure_manager(user)
    limit = get_settings().knowledge_max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"This file is too big (the limit is {get_settings().knowledge_max_upload_mb} MB).")
    try:
        text = extract.extract_text(filename, data)
    except extract.ExtractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    default_title = (filename or "Untitled").rsplit(".", 1)[0][:200]
    return add_document(db, user, (title or "").strip() or default_title, text, category,
                        filename=(filename or "")[:255], source="upload", request=request)


# ---------- reading ----------
def list_documents(db: Session) -> list[KnowledgeDocument]:
    return list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc(),
                                                              KnowledgeDocument.id.desc())))


def get_document(db: Session, document_id: int) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise access.not_found("Document")
    return document


def delete_document(db: Session, user: User, document_id: int, request: Request | None = None) -> None:
    access.ensure_manager(user)
    document = get_document(db, document_id)
    title = document.title
    db.delete(document)  # its passages are removed with it
    db.commit()
    audit_service.log_action(db, "knowledge_deleted", user.id, "knowledge_document", document_id, {"title": title}, request)


def stats(db: Session) -> dict:
    tag = embedding_tag()
    chunks = db.scalar(select(func.count(KnowledgeChunk.id))) or 0
    embedded = db.scalar(select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.embedding_model == tag)) or 0
    return {"documents": db.scalar(select(func.count(KnowledgeDocument.id))) or 0, "passages": chunks,
            "embedded_passages": embedded, "semantic_enabled": get_embeddings() is not None, "embedding_model": tag,
            "capacity": get_settings().knowledge_max_passages}


def reindex(db: Session, user: User, request: Request | None = None) -> dict:
    """Create vectors for passages that do not have one (or have one from an older model). Done in small
    batches so the free usage limit is respected: run it again if some remain."""
    access.ensure_manager(user)
    if get_embeddings() is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Semantic search is not set up. Add GOOGLE_API_KEY to .env (and keep KNOWLEDGE_SEMANTIC on).")
    tag = embedding_tag()
    todo = list(db.scalars(select(KnowledgeChunk).where(
        (KnowledgeChunk.embedding.is_(None)) | (KnowledgeChunk.embedding_model != tag))
        .order_by(KnowledgeChunk.id).limit(get_settings().embedding_max_per_reindex)))
    vectors = _embed_texts([c.text for c in todo])
    done = 0
    for chunk, vector in zip(todo, vectors):
        if vector is not None:
            chunk.embedding, chunk.embedding_model = vector, tag
            done += 1
    db.commit()
    result = {"embedded": done, "remaining": stats(db)["passages"] - stats(db)["embedded_passages"]}
    audit_service.log_action(db, "knowledge_reindexed", user.id, None, None, result, request)
    return result


# ---------- searching ----------
def search(db: Session, query: str, limit: int = 4) -> list[Hit]:
    settings = get_settings()
    query = (query or "").strip()[:500]
    if not query:
        return []
    rows = db.execute(
        select(KnowledgeChunk.id, KnowledgeChunk.document_id, KnowledgeChunk.text, KnowledgeChunk.embedding,
               KnowledgeChunk.embedding_model, KnowledgeDocument.title)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .order_by(KnowledgeChunk.id)).all()  # everything is searched: nothing is silently left out
    candidates = [Candidate(chunk_id=r[0], document_id=r[1], text=r[2], embedding=r[3], embedding_model=r[4], title=r[5])
                  for r in rows]
    keyword = bm25_rank(query, candidates)
    semantic: list = []
    tag = embedding_tag()
    embeddings = get_embeddings()
    if embeddings is not None and any(c.embedding and c.embedding_model == tag for c in candidates):
        try:
            semantic = semantic_rank(embeddings.embed_query(query), candidates, tag, settings.knowledge_min_similarity)
        except Exception:
            log.warning("Query embedding failed; using keyword search only", exc_info=True)
    return fuse(keyword, semantic, max(1, min(limit, 10)))


def knowledge_context(db: Session, query: str, limit: int = 3) -> tuple[str, list[str]]:
    """Passages for an AI prompt, plus the titles used. Never raises: no knowledge just means "(none)"."""
    try:
        hits = search(db, query, limit)
    except Exception:
        log.warning("Knowledge search failed", exc_info=True)
        return "(none)", []
    if not hits:
        return "(none)", []
    text = "\n\n".join(f"[{hit.title}]\n{hit.text}" for hit in hits)
    titles = list(dict.fromkeys(hit.title for hit in hits))
    return text, titles
