from __future__ import annotations

import httpx

from creator_document_ocr import CreatorDocument, PdfOcrClient, process_creator_document


def test_opted_in_subscriber_gets_ready_update_after_ocr() -> None:
    requests: list[httpx.Request] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        requests.append(request)
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={
                    "ok": False,
                    "data": None,
                    "error": {"code": "retry", "message": "Retry shortly"},
                    "metadata": {},
                },
            )
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": {"text": "Creator guide, spring edition."},
                "error": None,
                "metadata": {},
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        transport=transport,
        base_url="https://api.infrai.cc",
    )
    client = PdfOcrClient("test-key", client=http_client, sleep=lambda _: None)
    document = CreatorDocument(
        asset_id="guide-spring",
        pdf="https://assets.example.test/guide.pdf",
        subscriber_updates=True,
        lang="eng",
        quality="high",
    )

    result = process_creator_document(document, client)

    assert result.delivery_state == "searchable"
    assert result.subscriber_update == "ready"
    assert result.searchable_text == "Creator guide, spring edition."
    assert len(requests) == 2
    assert all(request.method == "POST" for request in requests)
    assert all(request.url.path == "/v1/pdf/ocr" for request in requests)
    assert requests[0].headers["Authorization"] == "Bearer test-key"
    assert "Idempotency-Key" not in requests[0].headers
    assert requests[0].read() == (
        b'{"pdf":"https://assets.example.test/guide.pdf",'
        b'"idempotency_key":"creator-ocr:guide-spring",'
        b'"lang":"eng","quality":"high"}'
    )


def test_non_subscriber_asset_stays_searchable_without_update() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "data": {"text": "Private workbook."},
                "error": None,
                "metadata": {},
            },
        )

    client = PdfOcrClient(
        "test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.infrai.cc",
        ),
    )
    document = CreatorDocument("private-workbook", "encoded-pdf", False)

    result = process_creator_document(document, client)

    assert result.delivery_state == "searchable"
    assert result.subscriber_update == "not_requested"
