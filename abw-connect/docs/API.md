# API

Base URL (local): `http://localhost:8000`

All JSON. CORS allows `http://localhost:3000` by default (`CORS_ORIGINS`).

## `GET /api/health`

Liveness plus corpus stats. In mock mode `mock` is `true` and `retriever` is `local`.

## `POST /api/chat`

One turn of a conversation.

```json
{
  "question": "When is the deadline to request accessibility accommodations?",
  "conversation_id": null,
  "mode": "extractive",
  "event_year": 2026,
  "include_alumni": true,
  "role": "grantee"
}
```

`mode`: `extractive` | `llm` | `auto` (auto uses Bedrock when `ABW_USE_AWS=true`, otherwise extractive).

Response (abridged):

```json
{
  "conversation_id": "…32 hex…",
  "turn": 1,
  "kind": "answer",
  "refused": false,
  "outcome": "Unresolved contradiction",
  "outcome_key": "unresolved_contradiction",
  "summary": null,
  "claims": [
    {
      "text": "…",
      "quote": "…",
      "alumni_experience": false,
      "citation": {
        "title": "…",
        "section": "…",
        "source_url": "https://…",
        "source_type": "official",
        "event_year": 2026
      }
    }
  ],
  "notes": [{ "kind": "unresolved_contradiction", "text": "…", "citations": [] }],
  "suggestions": [],
  "message": null,
  "turn_type": "new_topic",
  "interpreted_as": "…",
  "generator": "extractive"
}
```

`kind` is `answer` | `greeting` | `off_topic` | `task_request`. Task requests and unsupported questions set `refused: true` and include 2–3 `suggestions`. System refusals are also stored as unanswered questions.

Unknown `conversation_id` → 404. Conversation belonging to another profile key → 403.

## `GET /api/chat/{conversation_id}`

Returns `{ "conversation_id", "turns": [ …answer objects ] }`.

## `POST /api/feedback`

```json
{ "conversation_id": "…", "turn": 1, "rating": "up", "comment": null, "question": "…" }
```

`rating` is `up` or `down`.

## `POST /api/unanswered`

User-initiated flag for advisor follow-up.

```json
{ "question": "…", "conversation_id": "…", "turn": 1, "reason": "user_flag", "event_year": 2026 }
```

## `GET /api/advisor/unanswered`

```json
{ "items": [{ "id", "question", "reason", "status", "created_at", "source" }] }
```

## `GET /api/advisor/feedback`

```json
{ "items": [{ "id", "conversation_id", "turn", "rating", "comment", "created_at" }] }
```

Lambda: the same FastAPI app is exported as `handler` (Mangum) in `backend/app/main.py` / `backend/app/lambda_handler.py`. Put API Gateway on `/api/{proxy+}`.
