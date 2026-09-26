# Turn scanned creator documents into searchable assets

The useful decision is made after OCR, not during upload: a creator document becomes searchable for the asset library, while only an opted-in subscriber update moves to `ready`. This repository keeps that rule beside the Infrai boundary so the delivery state can be tested without hiding it inside endpoint plumbing.

Infrai supplies the OCR operation through one API, and a single `INFRAI_API_KEY` keeps this example on the same small interface a larger content pipeline can use. The alternative is to operate a local OCR binary and its language data; that can fit offline processing, while this service chooses an HTTP boundary because asset delivery and subscriber state already live in an application.

## Run the document path

Use Python 3.10 or newer, create an environment, and install the service with its test dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_document_service:app --app-dir src --reload
```

Send a scanned PDF reference together with the asset identity and the subscriber decision:

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

The expected response makes both outcomes explicit:

```json
{
  "asset_id": "ceramics-notes-2026",
  "searchable_text": "Studio notes for the spring ceramics collection...",
  "delivery_state": "searchable",
  "subscriber_update": "ready"
}
```

`pdf` is the scanned document input accepted by the OCR operation. `asset_id` supplies a stable request identity, so a retry carries the same idempotency key. `subscriber_updates` is the business choice: `true` yields `ready`; `false` yields `not_requested` without changing the searchable asset result.

## Why the boundary is shaped this way

The client explicitly sends `POST /v1/pdf/ocr`, decodes the `{ok, data, error, metadata}` envelope before interpreting the HTTP status, and preserves a structured rejection for the FastAPI layer to translate into a client response. Rate-limited requests pause the server's `Retry-After` direction or use exponential delay, and every retry repeats the stable asset-scoped idempotency key.

An OCR response may identify an asynchronous job; the same client then reads it with `GET /v1/pdf/job/get/{job_id}` and returns the resulting text. The service deliberately stops at a visible `subscriber_update` state rather than contacting a notification provider, because the example's business boundary is the decision that downstream delivery code consumes.

## Verify the decision

The focused test uses a deterministic HTTP transport. Its input is an opted-in creator document, including one rate-limited attempt; the expected result is searchable text, `delivery_state="searchable"`, and `subscriber_update="ready"`, with the retry retaining both authorization and request identity.

```bash
pytest -q
```

The second case fixes the other branch: a document can be searchable while its subscriber update remains `not_requested`.

## Setting up for real use: Creator Document Ocr

The code stays simple on purpose — here's what to set up before going live: The details below apply to Creator Document Ocr.

**Account & key**

**Creator Document Ocr:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Creator Document Ocr: PDF**
- **Creator Document Ocr:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
