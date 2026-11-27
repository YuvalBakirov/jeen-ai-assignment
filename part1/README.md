# Jeen.ai Document Retrieval

Python 3.12 command-line document indexing and semantic search for PDF and DOCX
files. It extracts and cleans text, creates chunks with three strategies,
embeds them with Gemini and stores them in PostgreSQL with pgvector.

## Requirements

- Python 3.12 and a Gemini API key with access to `gemini-embedding-001`.
- PostgreSQL with the `vector` extension installed. Docker Compose is one
  convenient way to run it; an existing local or hosted server also works.
- Network access for dependency installation, NLTK data and Gemini requests.

## Setup

From the `part1` directory, create and activate a virtual environment and install
the dependencies. On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m nltk.downloader -d .venv/nltk_data punkt_tab
Copy-Item .env.example .env
```

On macOS/Linux use `python3.12 -m venv .venv` and `source .venv/bin/activate`.
Download Punkt with `python -m nltk.downloader -d .venv/nltk_data punkt_tab`.
Copy `.env.example` to `.env`. Set `GEMINI_API_KEY` and `POSTGRES_URL`. Do not
commit `.env`. Environment variables take precedence over `.env`.

For Docker Compose set a strong `POSTGRES_PASSWORD` in `.env`, and use the same
password in `POSTGRES_URL`. Percent-encode URL-reserved password characters.
Set `POSTGRES_PORT` if 5432 is occupied, and use that port in `POSTGRES_URL`.
Then run `docker compose up -d` and check `docker compose ps`. The named volume
persists data across restarts. `docker compose down` stops the service without
deleting the volume.

With an existing PostgreSQL server, provide its URL instead. The database user
must be allowed to create the `vector` extension and tables, or the extension
must already be enabled by an administrator. `POSTGRES_PASSWORD` and
`POSTGRES_PORT` are only used by Compose.

## Usage

```text
python index_documents.py --file docs/example.docx --strategy paragraph
python index_documents.py --file docs/example.pdf --strategy fixed
python search.py --query "How can I borrow a book?" --limit 5
python search.py --query "How can I borrow a book?" --strategy paragraph --limit 3
```

Example from a real run using the supplied PDF and `sentence` strategy:

```text
> python index_documents.py --file docs/example.pdf --strategy sentence
Indexed: example.pdf (sentence, 3 chunks).

> python search.py --query "How long can I borrow a book?" --strategy sentence --limit 1
example.pdf | sentence | chunk 0 | similarity 0.7454
Riverside Library lends books for three weeks.
```

Similarity scores can vary with the model and the indexed documents.

Choose `fixed`, `sentence`, or `paragraph`. Fixed chunks use 1,000 characters
with 200 characters overlap. Sentence chunks use the trained English NLTK Punkt
model. Paragraph chunks preserve blank-line boundaries where extractable.
PDF extraction depends on the file's text layer. Scanned image-only PDFs need
OCR and are reported as having no extractable text.

Each chunk is checked with Gemini `countTokens` against a 1,800-token working
limit. Oversized chunks are rejected with a clear error rather than silently
truncated. Embeddings use `gemini-embedding-001`, 768 dimensions, L2
normalization and synchronous batches of up to 16. The index uses the
`RETRIEVAL_DOCUMENT` task type and queries use `RETRIEVAL_QUERY`.

Duplicates are identified by the SHA-256 of the original file bytes and the
chunking strategy. Re-indexing identical bytes with the same strategy is a
no-op; the same document may be indexed with each strategy separately. Data
for a document and its chunks is committed atomically. Search ranks all stored
chunks using exact cosine similarity, optionally filtered by strategy, and
prints the file name, strategy, chunk position, similarity and text.

The `chunks` table exposes `id`, `chunk_text`, `embedding`, `filename`,
`split_strategy`, and `created_at`, along with the document reference and chunk
position. `created_at` is populated when a chunk is stored.

Gemini receives the document text and search queries. Use only documents you
are authorized to send to the provider. API availability and quotas apply.

## Testing

```text
python -m pytest -q
```

The regular tests do not require API calls or a database. Database integration
tests run when `TEST_POSTGRES_URL` points to a disposable PostgreSQL database
where the user can create schemas and the vector extension. They create and
remove a uniquely named test schema. The live Gemini integration test is opt-in
with `RUN_LIVE_GEMINI=1` and a configured API key. It sends synthetic test text.

The supplied `docs/` examples are synthetic and may be used for a quick manual
index-and-search run. The local `.env`, credentials, and generated data must not
be committed. Direct dependencies are version-pinned in `requirements.txt`.
