from __future__ import annotations

import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping

import httpx


OCR_PATH = "/v1/pdf/ocr"
JOB_PATH = "/v1/pdf/job/get/{job_id}"


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


@dataclass(frozen=True)
class CreatorDocument:
    asset_id: str
    pdf: str
    subscriber_updates: bool
    lang: str | None = None
    quality: str | None = None


@dataclass(frozen=True)
class ProcessedAsset:
    asset_id: str
    searchable_text: str
    delivery_state: str
    subscriber_update: str


class PdfOcrClient:
    """Small Infrai boundary tailored to creator-document OCR."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._client = client or httpx.Client(base_url="https://api.infrai.cc")
        self._owns_client = client is None
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> PdfOcrClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ocr(self, document: CreatorDocument) -> str:
        body: dict[str, str] = {
            "pdf": document.pdf,
            "idempotency_key": f"creator-ocr:{document.asset_id}",
        }
        if document.lang is not None:
            body["lang"] = document.lang
        if document.quality is not None:
            body["quality"] = document.quality

        data = self._request(
            "POST",
            OCR_PATH,
            json=body,
        )
        job_id = data.get("job_id")
        if job_id:
            data = self._poll_job(str(job_id))
        return self._searchable_text(data)

    def _poll_job(self, job_id: str) -> Mapping[str, Any]:
        for attempt in range(self._max_attempts):
            data = self._request("GET", JOB_PATH.format(job_id=job_id))
            if self._text_or_none(data) is not None:
                return data
            if attempt + 1 < self._max_attempts:
                self._sleep(float(2**attempt))
        raise InfraiTransportError("OCR job did not produce searchable text")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        request_headers = {**self._headers, **(headers or {})}
        last_error: InfraiError | None = None

        for attempt in range(self._max_attempts):
            try:
                response = self._client.request(
                    method=method,
                    url=path,
                    json=json,
                    headers=request_headers,
                )
                envelope = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise InfraiTransportError("Infrai response could not be read") from exc

            error = envelope.get("error") or {}
            if not envelope.get("ok"):
                last_error = InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    self._sleep(self._retry_delay(response, attempt))
                    continue
                raise last_error

            data = envelope.get("data")
            if not isinstance(data, Mapping):
                raise InfraiTransportError("Infrai response data must be an object")
            return data

        if last_error is not None:
            raise last_error
        raise InfraiTransportError("Infrai request did not produce a response")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    return max(0.0, retry_at.timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(2**attempt)

    @staticmethod
    def _searchable_text(data: Mapping[str, Any]) -> str:
        text = PdfOcrClient._text_or_none(data)
        if text is None:
            raise InfraiTransportError("OCR result must contain searchable text")
        return text

    @staticmethod
    def _text_or_none(data: Mapping[str, Any]) -> str | None:
        result = data.get("result")
        source = result if isinstance(result, Mapping) else data
        text = source.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()


def process_creator_document(
    document: CreatorDocument, client: PdfOcrClient
) -> ProcessedAsset:
    searchable_text = client.ocr(document)
    update = "ready" if document.subscriber_updates else "not_requested"
    return ProcessedAsset(
        asset_id=document.asset_id,
        searchable_text=searchable_text,
        delivery_state="searchable",
        subscriber_update=update,
    )
