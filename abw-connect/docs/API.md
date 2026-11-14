# ABW Connect API Guide

Base URL: `<API_BASE>` (shared separately). All endpoints are under `/api`, take and return JSON, and need no auth key.
Browser calls are only accepted from allowed origins; for local dev use a Next.js dev proxy (see the end).

---

## 1. Health: `GET /api/health`
Is the backend up, and how is it configured?
Returns `status`, `retriever`, `knowledge_base`, `default_generator`, `bedrock_model_id`, `default_event_year`, counts of `unanswered` and `feedback`, and `git_sha` (the deployed commit).

---

## 2. Ask a question: `POST /api/chat`
The main endpoint. Sends a question and gets an LLM-generated, source-cited answer.

**Request**
| Field | Type | Required | Notes |
|---|---|---|---|
| `question` | string | yes | 1 to 2000 chars |
| `conversation_id` | string | no | 32 lowercase hex chars from a previous reply; omit to start a new chat |
| `mode` | `"llm"`, `"extractive"` or `"auto"` | no | use `"llm"` |
| `event_year` | int | no | defaults to 2026 |
| `include_alumni` | bool | no | default `true`; include alumni-experience docs |
| `role` | `"grantee"` or `"advisor"` | no | default `"grantee"` |

```json
{ "question": "What does the ABW grant cover?", "mode": "llm" }
```

**Response (main fields)**
| Field | What it is |
|---|---|
| `summary` | The answer to show the user |
| `kind` | e.g. `"answer"` |
| `refused` / `refusal` | `true` plus a reason when the bot couldn't answer from its sources |
| `claims[]` | Each supporting statement: `text`, `quote` (exact source text), `citation` |
| `claims[].citation` | `title`, `section`, `source_url`, `source_type` (`official` or `alumni`), `event_year`, `alumni_experience` |
| `conversation_id` | Send back on the next question to keep context |
| `turn` | Turn number in the conversation (needed for feedback) |
| `interpreted_as` | How a follow-up question was rewritten |
| `outcome`, `topic`, `latency_ms`, `generator`, `passages[]` | Trace details for a "View details" panel |

```json
{
  "summary": "The ABW grant covers a full conference pass, roundtrip flight, and hotel accommodations.",
  "kind": "answer",
  "refused": false,
  "claims": [{
    "text": "The ABW grant covers a full conference pass.",
    "quote": "Participants of the Program will receive the following benefits ...",
    "citation": { "title": "All Builders Welcome Grant Terms and Conditions", "source_type": "official", "source_url": "https://aws.amazon.com/...", "event_year": 2026 }
  }],
  "conversation_id": "0f15195a89dc469d8aa3fe114bf3818f",
  "turn": 1,
  "latency_ms": 3279
}
```
Answers take about 3 to 6 seconds, so show a loading state.

---

## 3. Load a conversation: `GET /api/chat/{conversation_id}`
Returns `{ conversation_id, turns: [...] }`.
Optional query params `role`, `event_year`, `include_alumni` must match what the chat was started with, otherwise you get 403. An unknown id gives 404 (start a new chat).

---

## 4. Feedback: `POST /api/feedback`
Thumbs up or down on an answer.

| Field | Type | Required | Notes |
|---|---|---|---|
| `conversation_id` | string | yes | 8 to 64 chars |
| `turn` | int | yes | at least 1, from the chat reply |
| `rating` | `"up"` or `"down"` | yes | |
| `comment` | string | no | up to 2000 chars |
| `question` | string | no | up to 2000 chars |

Returns `{ "id": "...", "ok": true }`.

---

## 5. Flag an unanswered question: `POST /api/unanswered`
When a user says "this didn't answer my question".

| Field | Type | Required | Notes |
|---|---|---|---|
| `question` | string | yes | 1 to 2000 chars |
| `conversation_id` | string | no | |
| `turn` | int | no | |
| `reason` | string | no | default `"user_flag"`, up to 80 chars |
| `event_year` | int | no | |

Returns `{ "id": "...", "ok": true }`.

---

## 6. Advisor: unanswered queue: `GET /api/advisor/unanswered`
Returns `{ "items": [...] }`: every flagged question, for advisors to review knowledge gaps.

## 7. Advisor: feedback list: `GET /api/advisor/feedback`
Returns `{ "items": [...] }`: every feedback entry.

Advisor endpoints have no login yet, and they show what real users asked. Don't display them publicly.

---

## Errors
- `422`: the request didn't match the fields above (FastAPI validation error with details).
- `403` / `404`: conversation problems (see section 3). Start a new chat.

## Local development
Add a dev-only proxy to `next.config.mjs` so the browser calls your own origin:
```js
async rewrites() {
  return process.env.NODE_ENV === "development"
    ? [{ source: "/api/:path*", destination: `${process.env.ABW_API_BASE}/api/:path*` }]
    : [];
}
```
Note: rewrites don't run with `output: "export"`, so apply `output: "export"` only for production builds.

## Example
```bash
curl -X POST "$ABW_API_BASE/api/chat" -H 'content-type: application/json' \
  -d '{"question":"What does the ABW grant cover?","mode":"llm"}'
```

---

## Reference details

**Running the backend locally:** base URL `http://localhost:8000`. CORS allows `http://localhost:3000` by default; set `CORS_ORIGINS` to change it.

**`mode`:** `auto` uses Bedrock when `ABW_USE_AWS=true` and falls back to extractive otherwise. In mock mode, `/api/health` reports `mock: true` and `retriever: local`.

**`kind`:** one of `answer`, `greeting`, `off_topic` or `task_request`. Task requests and unsupported questions set `refused: true` and include 2 or 3 `suggestions`. System refusals are also stored as unanswered questions.

**Other response fields:** `outcome_key`, `notes[]` (for example `{ "kind": "unresolved_contradiction", "text": "…", "citations": [] }`), `suggestions[]`, `message` and `turn_type` (for example `new_topic`).

**Document ids:** `claims[].citation.doc_id`, `claims[].citations[].doc_id` and `passages[].id` are Knowledge Base object keys such as `kb/official/2026/abw-terms.md#4`. Treat them as opaque strings. They never contain `s3://` URIs.

**Advisor item shapes:**

```json
{ "items": [{ "id": "…", "question": "…", "reason": "…", "status": "…", "created_at": "…", "source": "…" }] }
```

```json
{ "items": [{ "id": "…", "conversation_id": "…", "turn": 1, "rating": "up", "comment": "…", "created_at": "…" }] }
```

**Lambda:** the same FastAPI app is exported as `handler` (Mangum) in `backend/app/main.py` and `backend/app/lambda_handler.py`. API Gateway (HTTP API) proxies every route to it.
