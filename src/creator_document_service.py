from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from creator_document_ocr import (
    CreatorDocument,
    InfraiError,
    InfraiTransportError,
    PdfOcrClient,
    process_creator_document,
)


class CreatorDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1)
    pdf: str = Field(min_length=1)
    subscriber_updates: bool
    lang: str | None = None
    quality: str | None = None


class CreatorDocumentResponse(BaseModel):
    asset_id: str
    searchable_text: str
    delivery_state: str
    subscriber_update: str


app = FastAPI(title="Creator document OCR")


@app.post("/creator-documents/ocr", response_model=CreatorDocumentResponse)
def ocr_creator_document(request: CreatorDocumentRequest) -> CreatorDocumentResponse:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="INFRAI_API_KEY is required")

    document = CreatorDocument(**request.model_dump())
    try:
        with PdfOcrClient(api_key) as client:
            asset = process_creator_document(document, client)
    except InfraiError as exc:
        public_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        raise HTTPException(status_code=public_status, detail=detail) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CreatorDocumentResponse(**asset.__dict__)
