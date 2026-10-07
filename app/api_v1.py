"""Public API, authenticated with an X-API-Key header (keys are managed on the /account page)."""
from __future__ import annotations

import datetime as dt
import shutil

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from . import config
from .auth import api_user, get_db
from .errors import AppError
from .models import Case, User
from .report import build_pdf
from .services import add_document, audit, case_dir, case_payload, get_case, require_verified, run_analysis

router = APIRouter(prefix="/v1", tags=["api"])


@router.post("/dossier")
def create_dossier(request: Request, files: list[UploadFile] = File(...), title: str = Form(""),
                   user: User = Depends(api_user), db: Session = Depends(get_db)):
    """Upload 1..N documents, analyse them and return the findings. Costs 1 credit per document."""
    require_verified(user)
    if not 1 <= len(files) <= config.MAX_FILES_PER_REQUEST:
        raise AppError(400, "err.api_files_range", max=config.MAX_FILES_PER_REQUEST)
    case = Case(org_id=user.org_id, created_by=user.id, title=(title.strip() or f"API dossier {dt.date.today()}")[:300])
    db.add(case)
    db.flush()
    folder = case_dir(case)  # computed before any rollback
    try:
        for up in files:
            add_document(db, case, up.filename or "document", up.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1))
        run_analysis(db, user, case, request.state.lang)
        audit(db, user, "api.dossier", case.id)
        db.commit()
    except Exception:
        db.rollback()  # restores any credits debited in this request
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return case_payload(case, request.state.lang)


@router.get("/cases/{case_id}")
def get_dossier(case_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    return case_payload(get_case(db, user, case_id), request.state.lang)


@router.get("/cases/{case_id}/report.pdf")
def get_report(case_id: int, request: Request, user: User = Depends(api_user), db: Session = Depends(get_db)):
    case = get_case(db, user, case_id)
    if case.status != "analyzed":
        raise AppError(400, "err.not_analyzed")
    return Response(build_pdf(case, request.state.lang), media_type="application/pdf")
