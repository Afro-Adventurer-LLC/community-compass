# Knowledge base sources

Retrieved **2026-11-04**. Pages were fetched from the public web and converted to Markdown under `kb/`. Each file has a Bedrock Knowledge Bases sidecar (`*.metadata.json`, ≤ 1KB) with `source_url`, `event_year`, and `source_type` (`official` or `alumni_experience`). Optional `section` / `retrieval_date` are omitted when needed to stay under the sidecar size limit; see `scripts/slim_kb_metadata.py`.

| File | URL | Year | Type | Notes |
| --- | --- | --- | --- | --- |
| `kb/official/2026/faqs-*.md` | https://aws.amazon.com/events/reinvent/faqs/ | 2026 | official | Split by FAQ section. Accessibility FAQ states requests must be received by **November 14th**. |
| `kb/official/2026/abw-grant.md` | https://aws.amazon.com/events/reinvent/experiences/all-builders-welcome/ | 2026 | official | Applications closed; grant overview. |
| `kb/official/2026/abw-terms.md` | https://aws.amazon.com/events/reinvent/experiences/all-builders-welcome/all-builders-welcome-terms/ | 2026 | official | Section numbers 1–5 preserved. |
| `kb/official/2026/know-before-you-go.md` | https://aws.amazon.com/events/reinvent/know-before-you-go/ | 2026 | official | |
| `kb/official/2026/agenda.md` | https://aws.amazon.com/events/reinvent/agenda/ | 2026 | official | High-level week view. Some keynote titles on later weekdays were unlabeled in the source HTML. |
| `kb/official/2026/accessibility-services.md` | https://aws.amazon.com/events/reinvent/plan/accessibility-services/ | 2026 | official | Advance-request deadline **Nov. 13, 2026**. |
| `kb/alumni/2025-first-time-abw-grant.md` | https://builder.aws.com/content/36ZF1aPahQtQqlcnk0gaNw7jQzY/my-first-time-experiencing-aws-reinvent-thanks-to-the-abw-grant | 2025 | alumni_experience | Personal experience; must not override official guidance. |
| `kb/alumni/2023-newcomers-guide.md` | https://www.pluralsight.com/resources/blog/cloud/newcomers-guide-to-aws-reinvent | 2023 | alumni_experience | Historical application tips; labeled personal experience. |

All eight source URLs were retrieved successfully. No content was invented for missing pages.

Known official conflict used as an eval case: the re:Invent FAQ accessibility section says accommodation requests must be received by November 14th, while the accessibility services page says the deadline for all requests is Nov. 13, 2026. The assistant must surface both cited values and ask the user to confirm with support.
