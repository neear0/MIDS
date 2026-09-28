from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app import audit
from app.ai.explain import explain
from app.ai.extraction import ExtractionError, get_extractor
from app.api.deps import DB, WRITE_ROLES, CurrentUser, company_for
from app.api.invoices import _read_upload
from app.config import get_settings
from app.validation.engine import validate_invoice

router = APIRouter(tags=["ai"])


@router.post("/companies/{company_id}/extract")
async def extract(company_id: int, user: CurrentUser, db: DB, file: UploadFile = File(...)) -> dict:
    """Upload a PDF/scan/photo → draft invoice + validation findings. Nothing is stored."""
    company = company_for(db, user, company_id, WRITE_ROLES)
    data = await _read_upload(file)
    media_type = (file.content_type or "").split(";")[0]
    if media_type == "application/octet-stream" and data[:4] == b"%PDF":
        media_type = "application/pdf"
    try:
        result = get_extractor().extract(data, media_type)
    except ExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    inv = result.invoice
    direction = "incoming" if company.dic and inv.buyer.dic == company.dic else (
        "outgoing" if company.dic and inv.seller.dic == company.dic else "unknown")
    audit.record(db, action="document.extracted", company_id=company_id, user_id=user.id, entity_type="document",
                 details={"filename": file.filename, "provider": result.provider, "confidence": result.confidence})
    db.commit()
    return {**result.model_dump(mode="json"), "direction_guess": direction,
            "validation": validate_invoice(inv).as_dict()}


class ExplainIn(BaseModel):
    question: str = ""
    rule_id: str | None = None
    context: str | None = None


@router.post("/explain")
def explain_endpoint(body: ExplainIn, user: CurrentUser) -> dict:
    settings = get_settings()
    use_llm = settings.extraction_provider == "anthropic" or bool(settings.anthropic_api_key)
    return explain(body.question, body.rule_id, body.context, use_llm=use_llm,
                   api_key=settings.anthropic_api_key, model=settings.anthropic_model)
