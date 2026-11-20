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
| `kb/alumni/2026-mentee-preparation-guide.md` | Uploaded `ABW_Mentee_Preparation_Guide.pdf`; no public URL supplied | 2026 | alumni_experience | Mentor-prepared checklist added 2026-11-14. Time-sensitive details are marked for confirmation and must not override official guidance. |

### Community articles added 2026-11-14

Sourced from the team's "Article KB for builder compass" list. Each file summarizes the practical tips in our own words with the author and a link back; no article text is copied. Community posts are `alumni_experience` (they must never override official guidance); the two AWS-authored pages are `official`.

| File | URL | Year | Type | Notes |
| --- | --- | --- | --- | --- |
| `kb/official/2026/session-types.md` | https://aws.amazon.com/events/reinvent/sessions/how-youll-learn/ | 2026 | official | Formats and levels 100–500. |
| `kb/official/2026/ai-ml-track-guide.md` | https://aws.amazon.com/blogs/machine-learning/the-attendees-guide-to-the-aws-reinvent-2026-ai-ml-track/ | 2026 | official | AWS ML Blog, Nov 11, 2026. Starter session codes and AWS Village. |
| `kb/alumni/2026-attendee-playbook-series.md` | https://builder.aws.com/content/3M1jaspZoTns1i16WgWGvGtrMPy/aws-reinvent-2026-the-attendee-playbook-series-index-start-here | 2026 | alumni_experience | Community guide by an AWS employee. Campus clusters, walk/shuttle times, keynote and Expo hours. Lists Caesars Forum for badge pickup, which the official agenda does not. |
| `kb/alumni/2026-abw-insiders-guide.md` | https://builder.aws.com/content/3FGF2bDqKm6xKGmyJqJMrcwRhE8/the-aws-all-builders-welcome-grant-an-insiders-guide-for-applicants | 2026 | alumni_experience | Alumni advisor's account of grant benefits ($250 gift card, $75 ride voucher, exam voucher) that the official Terms do not list. |
| `kb/alumni/2025-what-i-wish-i-knew.md` | https://builder.aws.com/content/3Eo2OsiX5x8VgcdYmOSKJZS3Com/what-i-wish-i-knew-before-aws-reinvent | 2025 | alumni_experience | Published Nov 2026; venues match 2025. |
| `kb/alumni/2025-know-before-you-go-in-person.md` | https://builder.aws.com/content/35iYepTKrrpDlEVwLGuPPfJ6X4y/know-before-you-go-attending-reinvent-2025-in-person | 2025 | alumni_experience | Community guide by an AWS employee; 2025 venues and transport. Expired discount code left out. |
| `kb/alumni/2025-abw-what-actually-matters.md` | https://builder.aws.com/content/37apPsVaYgA1hMbWoPPYWfe0Xas/three-weeks-after-reinvent-what-actually-matters-when-50000-builders-gather | 2025 | alumni_experience | |
| `kb/alumni/2025-builders-handbook.md` | https://builder.aws.com/content/37gJtkalSHyUd1Gv1nxVgC5lZ3g/the-reinvent-builders-handbook | 2025 | alumni_experience | |
| `kb/alumni/2025-abw-grant-applicant-guide.md` | https://builder.aws.com/content/2yDdWKuCX1zMBBSuIAGZ45LPv8N | 2025 | alumni_experience | |
| `kb/alumni/2025-alumni-advisor-reflection.md` | https://suzanamelo.com/articles/flying-to-the-cloud-and-beyond/ | 2025 | alumni_experience | |
| `kb/alumni/2024-first-timer-tips-abw.md` | https://builder.aws.com/content/2rC137ImwpsXdAXO91J6ADCx0HG | 2024 | alumni_experience | |
| `kb/alumni/2024-priorities.md` | https://builder.aws.com/content/2rAqfD3OmAI8yRuu475tyRJ2odf/aws-reinvent-2024-priorities | 2024 | alumni_experience | |
| `kb/alumni/2024-abw-first-time-attendee.md` | https://builder.aws.com/content/2zNV1Kmz2ZDAJLpbzC0XKJ0xWwK/aws-reinvent-2024-experience-first-time-attendee-with-all-builders-welcome-grant | 2024 | alumni_experience | |
| `kb/alumni/2024-abw-grant-journey.md` | https://builder.aws.com/content/2qMht5y77H3KPBAVkaZOueju7p5/a-journey-to-the-heart-of-technological-innovation-re-invent2024 | 2024 | alumni_experience | Mostly a launch recap; little attendee advice. |
| `kb/alumni/2024-abw-grant-experience-figueroa.md` | https://www.alejofig.com/posts/reinvent/ | 2024 | alumni_experience | Year inferred from post dates. |
| `kb/alumni/2023-decoding-reinvent-first-timers.md` | https://builder.aws.com/content/2hWXbTzR6PQmvm6wtHPddeOjgaQ/decoding-aws-reinvent-or-a-guide-for-first-timers | 2023 | alumni_experience | Session code format. |
| `kb/alumni/2023-recap-community-builder.md` | https://dev.to/aws-builders/recapping-reinvent-2023-mm3 | 2023 | alumni_experience | |

Not added from that list: LinkedIn posts (need a login to read; add only with the author's permission); the AWS Builder Center topic pages for re:Invent recaps and the Hiroko Nishimura archive page (index pages with no article text when fetched); the 2025 AWS Partner guide (2025 official content would be filtered out of 2026 answers). Already in the KB: the 2025 first-time ABW post and the official Know Before You Go, FAQ and Agenda pages.

The original eight public source URLs were retrieved successfully. The mentee preparation guide was supplied as a PDF without a public source URL. No content was invented for missing pages.

Known official conflict used as an eval case: the re:Invent FAQ accessibility section says accommodation requests must be received by November 14th, while the accessibility services page says the deadline for all requests is Nov. 13, 2026. The assistant must surface both cited values and ask the user to confirm with support.
