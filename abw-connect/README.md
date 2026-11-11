# ABW Connect

Source-backed assistant for **AWS All Builders Welcome (ABW)** grant recipients and alumni advisors.

The app retrieves from official re:Invent / ABW pages (and labeled alumni experience), checks that the sources actually support an answer, resolves conflicts, generates claims, and **drops any claim whose quote is not verbatim in the source** or whose numbers/dates do not match that quote.

- Frontend: Next.js + Tailwind at http://localhost:3000
- Backend: Python FastAPI at http://localhost:8000 (Lambda-ready via Mangum)
- Default **mock mode**: local lexical index over `kb/`, in-memory store, extractive generator — **no AWS credentials**
- Real AWS is opt-in (`ABW_USE_AWS=true`): Bedrock Knowledge Bases Retrieve, Bedrock Converse, DynamoDB

## Quick start

See [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md).

```bash
# backend
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (another terminal)
cd frontend && npm install && npm run dev
```

## Docs

- [High-level design](docs/HLD.md)
- [API](docs/API.md)
- [Local setup](docs/LOCAL_SETUP.md)
- [AWS deployment](docs/AWS_DEPLOY.md)
- [Knowledge base sources](docs/KB_SOURCES.md)

## Tests

```bash
pip install -r backend/requirements.txt
pytest -q
PYTHONPATH=backend python -m evals.run_evals
```

## Repo layout

```
frontend/     Next.js chat UI + advisor view
backend/      FastAPI app (routes, RAG pipeline, mocks)
kb/           Markdown sources + Bedrock metadata sidecars
tests/        API, unit, integration
evals/        Per-item and multi-turn cases
docs/         HLD, API, local setup, AWS deploy
scripts/      Upload kb/ to S3 and start a KB ingestion job
```
