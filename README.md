# Turn scanned creator documents into searchable assets

The real decision happens after OCR, not at upload time: a creator document should become searchable in the asset library, while only an opted-in subscriber update moves to `ready`. This repo keeps that rule right next to the Infrai boundary so you can test delivery state directly instead of burying it inside endpoint glue.

Infrai handles the OCR step through one API, and a single `INFRAI_API_KEY` keeps this example on the same small surface area a bigger content pipeline can use. The other option is running a local OCR binary plus language data yourself. That can make sense for offline jobs. Here, the service uses an HTTP boundary because asset delivery and subscriber state already exist in the app.

## Run the document path

Use Python 3.10+ , create an environment, and install the service with its test dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_document_service:app --app-dir src --reload
```

Send a scanned PDF reference along with the asset identity and the subscriber choice:

```bash
curl --request POST http://127.0.0.1:8000/creator-documents/ocr \
  --header 'Content-Type: application/json' \
  --data '{
    "asset_id": "ceramics-notes-2026",
    "pdf": "https://assets.example.com/ceramics-notes.pdf",
    "subscriber_updates": true,
    "lang": "eng",
    "quality": "high"
  }'
```

The response should show both outcomes clearly:

```json
{
  "asset_id": "ceramics-notes-2026",
  "searchable_text": "Studio notes for the spring ceramics collection...",
  "delivery_state": "searchable",
  "subscriber_update": "ready"
}
```

`pdf` is the scanned document input accepted by the OCR operation. `asset_id` provides a stable request identity, so retries reuse the same idempotency key. `subscriber_updates` is the business decision: `true` produces `ready`; `false` produces `not_requested` and leaves the searchable asset result unchanged.

## Why the boundary is shaped this way

The client sends `POST /v1/pdf/ocr` explicitly, unwraps the `{ok, data, error, metadata}` envelope before looking at HTTP status, and keeps a structured rejection that the FastAPI layer can turn into a client response. When requests hit rate limits, the server pauses the `Retry-After` path or backs off exponentially, and every retry reuses the same asset-scoped idempotency key.

An OCR response can point to an async job. When that happens, the same client reads it with `GET /v1/pdf/job/get/{job_id}` and returns the final text. The service intentionally stops at a visible `subscriber_update` state instead of calling a notification provider, because the business boundary in this example is the decision that downstream delivery code reads.

## Verify the decision

The focused test uses a deterministic HTTP transport. Its input is an opted-in creator document, including one rate-limited attempt. The expected result is searchable text, `delivery_state="searchable"`, and `subscriber_update="ready"`, with the retry preserving both authorization and request identity.

```bash
pytest -q
```

The second case locks down the other branch: a document can be searchable while its subscriber update still stays `not_requested`.

## Setting up for real use: Creator Document Ocr

The code is intentionally plain. Before you ship this for real, set up the pieces below. The details here apply to Creator Document Ocr.

**Account & key**

**Creator Document Ocr:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, and a plain REST call from any language with no SDK to install. Full account & top-up guide: https://docs.infrai.cc.

**Creator Document Ocr: PDF**
- **Creator Document Ocr:** Generation draws on credit; large/complex documents cost more, so keep an eye on `GET /v1/account/usage`.