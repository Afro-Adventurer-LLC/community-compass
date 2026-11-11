# Local setup

The MVP runs fully offline in **mock mode**: a lexical index over `kb/`, an in-memory store, and the extractive generator. You do **not** need AWS credentials.

## Prerequisites

- Python 3.11+ (3.12 is fine)
- Node.js 20+
- npm

## Backend (http://localhost:8000)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # optional; defaults already mock
uvicorn app.main:app --reload --port 8000
```

Check: `curl -s http://localhost:8000/api/health`

## Frontend (http://localhost:3000)

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000. Ask an ABW question (try *When is the deadline to request accessibility accommodations?* to see the Nov 13 vs 14 conflict). Open http://localhost:3000/advisor for unanswered questions and feedback.

## Tests and evals

From the repo root, with the backend virtualenv active (or `PYTHONPATH=backend`):

```bash
pip install -r backend/requirements.txt
pytest -q
PYTHONPATH=backend python -m evals.run_evals
```

Both must pass without AWS credentials. The tree must not mention the previous prototype's institution or its academic-policy corpus.

## Optional: real AWS

1. Copy `backend/.env.example` to `backend/.env`.
2. Set `ABW_USE_AWS=true`, `AWS_REGION`, and either `AWS_PROFILE` or the usual AWS env vars. **Never commit credentials.**
3. Set `BEDROCK_KB_ID`, `BEDROCK_MODEL_ID`, `DDB_TABLE_PREFIX`, and `S3_KB_BUCKET`.
4. Upload and ingest: `python scripts/upload_kb.py`
5. Create DynamoDB tables as in [AWS_DEPLOY.md](./AWS_DEPLOY.md).

`GENERATOR_MODE=llm` then uses Bedrock Converse. Timeouts fall back to extractive and the response includes `generator_error`.
