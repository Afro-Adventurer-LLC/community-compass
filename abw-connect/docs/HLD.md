# ABW Connect – High-Level Design

## 1. Overview

ABW Connect is an AI-powered community assistant for AWS All Builders Welcome (ABW) grant recipients and alumni advisors. It uses retrieval-augmented generation (RAG) over official re:Invent / ABW pages and labeled alumni experience, then **verifies every claim** against the retrieved source text before showing it.

Architecture preference: AWS-managed services so a small team can ship without running servers.

## 2. Technology stack

| Component | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Next.js + Tailwind CSS | Chat interface and advisor dashboard |
| Frontend hosting | AWS Amplify Hosting | Managed frontend hosting and Git CI/CD |
| API layer | Amazon API Gateway | HTTPS REST to the backend |
| Backend | Python FastAPI on AWS Lambda (Mangum) | Orchestration: retrieve → support check → resolve → generate → verify |
| Generation | Amazon Bedrock Converse (model id configurable) | Cited JSON claims; timeout falls back to extractive |
| Retrieval | Amazon Bedrock Knowledge Bases **Retrieve** (not RetrieveAndGenerate) | Passages from S3 documents |
| Document storage | Amazon S3 + `kb/` in repo | Markdown sources and `.metadata.json` sidecars |
| Application database | Amazon DynamoDB | Chat history, feedback, unanswered questions |
| Auth (later) | Amazon Cognito | Not required for the local MVP |
| DNS | Amazon Route 53 | Custom domain when deployed |

Local-dev mapping: frontend `localhost:3000`, backend `localhost:8000`, DynamoDB and Bedrock replaced by in-memory / lexical mocks unless `ABW_USE_AWS=true`.

## 3. Request flow

1. A grantee or advisor submits a natural-language question in the Amplify-hosted (or local) UI.
2. The frontend POSTs `/api/chat` to API Gateway (or the local FastAPI server).
3. The backend classifies greetings and task requests ("write an email for me") before retrieval.
4. Follow-ups are rewritten into a standalone question. Conversation history is **never used as evidence**.
5. Lambda (or FastAPI) calls Bedrock Knowledge Bases **Retrieve**, or the local lexical index in mock mode. Metadata filters use `event_year` and `source_type`.
6. Support check: if nothing relevant is retrieved, the assistant refuses, suggests 2–3 answerable questions, and logs an unanswered row for advisors.
7. Conflict resolver classifies official sources as compatible / explicit exception / superseded / unresolved contradiction. Alumni experience is labeled and **never overrides official guidance**.
8. Generator (Bedrock Converse or extractive) emits claims with verbatim quotes.
9. Verifier keeps a claim only if the quote occurs in the stored source and every number/date/period in the claim appears in that quote.
10. The UI renders the answer, citation chips, alumni badge, and conflict callout. Feedback and "flag as unanswered" write to DynamoDB (or the memory store).

## 4. Knowledge base ingestion

1. Editors add Markdown (and sidecars) under `kb/`.
2. `python scripts/upload_kb.py` copies objects to S3 and starts a Bedrock KB ingestion job.
3. Bedrock parses, chunks, embeds, and indexes the corpus.
4. Runtime retrieval is **Retrieve only**; generation and verification stay in the application.

## 5. Design constraints

- Prefer AWS-managed and serverless services.
- Every shown claim is source-backed and verified.
- Refuse rather than guess; escalate unanswered questions to alumni advisors.
- Official guidance outranks alumni experience.
- No credentials in the repository. Mock mode is the default so the public repo and tests need no AWS account.
