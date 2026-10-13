"""The Knowledge page: see, search, add and remove company documents."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import page_user
from app.models.user import User
from app.routers.crm_pages import back, error_text
from app.routers.knowledge import read_upload
from app.routers.pages import render
from app.services import access, knowledge_service

router = APIRouter(include_in_schema=False)


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, q: str = "", user: User = Depends(page_user), db: Session = Depends(get_db)):
    hits = knowledge_service.search(db, q, 5) if q.strip() else []
    return render(request, "knowledge.html", user, active="knowledge", q=q, hits=hits, searched=bool(q.strip()),
                  documents=knowledge_service.list_documents(db), stats=knowledge_service.stats(db),
                  categories=knowledge_service.CATEGORIES, can_manage=access.is_manager(user))


@router.post("/knowledge/reindex")
def knowledge_reindex(request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        result = knowledge_service.reindex(db, user, request)
    except HTTPException as exc:
        return back("/knowledge", error=error_text(exc))
    if result["remaining"]:
        return back("/knowledge", msg=f"Indexed {result['embedded']} passages; {result['remaining']} still to do. "
                                      "Wait a minute and press the button again.")
    return back("/knowledge", msg=f"Done: {result['embedded']} passages indexed for search by meaning.")


@router.post("/knowledge")
def knowledge_add(request: Request, title: str = Form(""), category: str = Form("other"), text: str = Form(""),
                  file: UploadFile | None = File(None), user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        if file is not None and file.filename:
            document = knowledge_service.add_uploaded_file(db, user, file.filename, read_upload(file), title,
                                                           category, request)
        else:
            document = knowledge_service.add_document(db, user, title, text, category, request=request)
    except HTTPException as exc:
        return back("/knowledge", error=error_text(exc))
    embedded = sum(1 for c in document.chunks if c.embedding is not None)
    note = (f"Added with {document.chunk_count} passages" +
            (" (search by meaning is on)." if embedded == document.chunk_count and embedded else
             ". Keyword search works now; use Re-index later for search by meaning." if document.chunk_count else "."))
    return back(f"/knowledge/{document.id}", msg=note)


@router.get("/knowledge/{document_id}", response_class=HTMLResponse)
def knowledge_document(document_id: int, request: Request, user: User = Depends(page_user),
                       db: Session = Depends(get_db)):
    return render(request, "knowledge_doc.html", user, active="knowledge",
                  document=knowledge_service.get_document(db, document_id), can_manage=access.is_manager(user))


@router.post("/knowledge/{document_id}/delete")
def knowledge_delete(document_id: int, request: Request, user: User = Depends(page_user), db: Session = Depends(get_db)):
    try:
        knowledge_service.delete_document(db, user, document_id, request)
    except HTTPException as exc:
        return back("/knowledge", error=error_text(exc))
    return back("/knowledge", msg="Document deleted.")
