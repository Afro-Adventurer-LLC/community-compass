import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ChatResponse } from "../services/api.ts";
import {
  composePrimaryAnswer,
  detailNotes,
  formatHealthStatus,
  hasTraceDetails,
  isRefusalLike,
  safetyNotes,
  shortGenerator,
  uniqueClaimTexts,
  conflictDocIds,
} from "./presentAnswer.ts";

function answer(partial: Partial<ChatResponse>): ChatResponse {
  return {
    conversation_id: "x",
    turn: 1,
    question: "q",
    kind: "answer",
    refused: false,
    claims: [],
    notes: [],
    ...partial,
  };
}

describe("composePrimaryAnswer", () => {
  it("uses the verified summary when present, not the individual claims", () => {
    const text = composePrimaryAnswer(
      answer({
        summary: "The grant covers a conference pass, roundtrip flight, and hotel.",
        claims: [
          {
            text: "Participants receive Program Benefits.",
            quote: "benefits (\"Program Benefits\")",
            citation: {
              doc_id: "t",
              title: "Terms",
              section: "1.4",
              source_url: "https://example",
              event_year: 2026,
              source_type: "official",
            },
          },
        ],
      }),
    );
    assert.equal(text, "The grant covers a conference pass, roundtrip flight, and hotel.");
    assert.equal(text.includes("Participants receive"), false);
  });

  it("does not dump retrieved excerpts or invent a canned answer when there is no LLM summary", () => {
    const termsDump =
      'These AWS All Builders Welcome Grant Program Terms & Conditions (these "Terms") contain the terms ' +
      'and conditions that govern your participation. D. you have not previously accepted a grant. ' +
      'Limitation of Liability. Section 1.7 Termination.';
    const cit = {
      doc_id: "t",
      title: "Terms",
      section: "1.4",
      source_url: "https://example",
      event_year: 2026,
      source_type: "official" as const,
    };
    const text = composePrimaryAnswer(
      answer({
        summary: null,
        claims: [
          { text: termsDump, quote: termsDump, citation: cit },
          {
            text: "A full conference pass to the Event you applied for;",
            quote: "A full conference pass to the Event you applied for;",
            citation: cit,
          },
        ],
      }),
    );
    assert.equal(text, "");
    assert.equal(/These AWS All Builders Welcome Grant Program Terms/.test(text), false);
    assert.equal(/Limitation of Liability/.test(text), false);
  });

  it("does not invent claims: empty verified data yields an empty narrative", () => {
    assert.equal(composePrimaryAnswer(answer({ summary: null, claims: [] })), "");
  });

  it("keeps refusal and task-request copy as primary content", () => {
    assert.equal(
      composePrimaryAnswer(
        answer({ kind: "task_request", refused: true, message: "I can't write an email for you." }),
      ),
      "I can't write an email for you.",
    );
    assert.equal(isRefusalLike(answer({ kind: "off_topic", refused: false })), true);
  });

  it("does not lead an unresolved conflict with a single definitive date or a canned template", () => {
    const cit = {
      doc_id: "a",
      title: "Accessibility",
      section: "How to request",
      source_url: "https://example",
      event_year: 2026,
      source_type: "official" as const,
    };
    const claims = [
      {
        text: "The deadline for all requests is Nov. 13, 2026.",
        quote: "The deadline for all requests is Nov. 13, 2026.",
        citation: cit,
      },
      {
        text: "All requests must be received by November 14th.",
        quote: "all requests must be received by November 14th.",
        citation: { ...cit, doc_id: "faq", title: "FAQs" },
      },
    ];
    const onesided = composePrimaryAnswer(
      answer({
        outcome_key: "unresolved_contradiction",
        summary: "The deadline for all requests is Nov. 13, 2026",
        claims,
      }),
    );
    assert.equal(/Please confirm with AWS event support/i.test(onesided), false);
    assert.equal(/^The official sources disagree: one says/i.test(onesided), false);
    const canned = composePrimaryAnswer(
      answer({
        outcome_key: "unresolved_contradiction",
        summary:
          "The official sources disagree: one says Nov. 13, 2026 and the other says November 14th. " +
          "Please confirm with AWS event support before relying on either date.",
        claims,
      }),
    );
    assert.equal(canned, "");
    const llm = composePrimaryAnswer(
      answer({
        outcome_key: "unresolved_contradiction",
        summary:
          "Official pages list two different request-by dates: Nov. 13, 2026 and November 14th. I cannot tell which governs.",
        claims,
      }),
    );
    assert.match(llm, /13/);
    assert.match(llm, /14/);
    assert.equal(/^The deadline for all requests is/i.test(llm), false);
    assert.equal(/Please confirm with AWS event support before relying on either date/i.test(llm), false);
  });

  it("does not let claim order compose a conflict winner", () => {
    const cit = {
      doc_id: "a",
      title: "A",
      section: "",
      source_url: "",
      event_year: 2026,
      source_type: "official" as const,
    };
    const c13 = {
      text: "The deadline for all requests is Nov. 13, 2026.",
      quote: "The deadline for all requests is Nov. 13, 2026.",
      citation: cit,
    };
    const c14 = {
      text: "all requests must be received by November 14th.",
      quote: "all requests must be received by November 14th.",
      citation: cit,
    };
    const prose =
      "One page lists Nov. 13, 2026 and another lists November 14th; the sources conflict.";
    const a = composePrimaryAnswer(
      answer({ outcome_key: "unresolved_contradiction", summary: prose, claims: [c14, c13] }),
    );
    const b = composePrimaryAnswer(
      answer({ outcome_key: "unresolved_contradiction", summary: prose, claims: [c13, c14] }),
    );
    assert.equal(a, b);
    assert.equal(a, prose);
  });

  it("keeps an LLM venue-time summary instead of inventing an event-date conflict", () => {
    const cit = {
      doc_id: "official/2026/know-before-you-go",
      title: "Know before you go",
      section: "Plan your schedule",
      source_url: "https://example",
      event_year: 2026,
      source_type: "official" as const,
    };
    const text = composePrimaryAnswer(
      answer({
        summary: "Allow 30 to 45 minutes between venues, and additional time for travel between properties.",
        claims: [
          {
            text: "Allow 30 to 45 minutes between venues.",
            quote: "allow 30 to 45 minutes between venues",
            citation: cit,
          },
        ],
      }),
    );
    assert.match(text, /30/);
    assert.equal(/disagree/i.test(text), false);
    assert.equal(/December|Nov\.?\s*30/i.test(text), false);
  });

  it("does not use Agenda December 4 when the conflict is Nov. 13 vs November 14th", () => {
    const a11y = {
      doc_id: "official/2026/accessibility-services",
      title: "Accessibility services at re:Invent 2026",
      section: "How to request a service",
      source_url: "https://example",
      event_year: 2026,
      source_type: "official" as const,
    };
    const faq = { ...a11y, doc_id: "official/2026/faqs-accessibility", title: "re:Invent 2026 FAQs — Accessibility services" };
    const agenda = { ...a11y, doc_id: "official/2026/agenda", title: "Agenda" };
    const text = composePrimaryAnswer(
      answer({
        outcome_key: "unresolved_contradiction",
        summary:
          "Official accessibility pages conflict: one lists Nov. 13, 2026 and another lists November 14th.",
        claims: [
          {
            text: "The deadline for all requests is Nov. 13, 2026.",
            quote: "The deadline for all requests is Nov. 13, 2026.",
            citation: a11y,
          },
          {
            text: "The event runs through Friday, December 4.",
            quote: "Friday, December 4",
            citation: agenda,
          },
        ],
        notes: [
          {
            kind: "unresolved_contradiction",
            text: "These two official sources disagree.",
            citations: [a11y, faq],
          },
        ],
      }),
    );
    assert.match(text, /conflict|differ|disagree/i);
    assert.match(text, /13/);
    assert.match(text, /14/);
    assert.equal(/December|\bDec\.?\s*4\b/i.test(text), false);
  });
});

describe("safety vs detail notes", () => {
  it("keeps contradiction status labels in View details, not as a second primary sentence", () => {
    const notes = [
      { kind: "unresolved_contradiction", text: "Unresolved contradiction · Accessibility · FAQs" },
      { kind: "alumni_experience", text: "Some passages are personal alumni experience." },
    ];
    const safety = safetyNotes(notes);
    assert.equal(safety.length, 0);
    const details = detailNotes(notes);
    assert.equal(details.some((n) => n.kind === "unresolved_contradiction"), true);
    assert.equal(details.some((n) => n.kind === "alumni_experience"), true);
  });
});

describe("uniqueClaimTexts", () => {
  it("drops duplicate claim text", () => {
    const c = {
      text: "Same fact.",
      quote: "Same fact.",
      citation: {
        doc_id: "t",
        title: "T",
        section: "",
        source_url: "",
        event_year: 2026,
        source_type: "official",
      },
    };
    assert.deepEqual(uniqueClaimTexts([c, { ...c }]), ["Same fact."]);
  });
});

describe("hasTraceDetails", () => {
  it("is true when claims or technical fields exist", () => {
    assert.equal(hasTraceDetails(answer({})), false);
    assert.equal(hasTraceDetails(answer({ generator: "extractive", latency_ms: 12 })), true);
  });
});

describe("formatHealthStatus", () => {
  it("does not imply an empty corpus in Bedrock mode when local index count is 0", () => {
    const label = formatHealthStatus({
      mock: false,
      retriever: "bedrock",
      documents: 0,
      default_generator: "llm:bedrock:amazon.nova-lite-v1:0",
      knowledge_base: true,
    });
    assert.equal(/0 docs/i.test(label), false);
    assert.match(label, /Knowledge base/i);
    assert.match(label, /Bedrock Retrieve/i);
  });

  it("still shows the local document count in mock mode", () => {
    const label = formatHealthStatus({
      mock: true,
      retriever: "local",
      documents: 12,
      default_generator: "extractive",
    });
    assert.match(label, /12 local docs/);
    assert.match(label, /mock/);
  });

  it("appends a short git sha when health reports one", () => {
    const label = formatHealthStatus({
      mock: false,
      retriever: "bedrock",
      documents: 0,
      default_generator: "llm:bedrock:amazon.nova-lite-v1:0",
      knowledge_base: true,
      git_sha: "17b43c7972cfb88a357070e76284a735a5f344d6",
    });
    assert.match(label, /17b43c7/);
    assert.equal(/0 docs/i.test(label), false);
  });
});

describe("shortGenerator", () => {
  it("shortens Bedrock model ids", () => {
    assert.equal(shortGenerator("extractive"), "extractive");
    assert.match(shortGenerator("llm:bedrock:amazon.nova-lite-v1:0") || "", /nova-lite/i);
  });
});

describe("conflictDocIds", () => {
  it("treats bucket-relative kb/ doc ids as opaque strings", () => {
    const id = "kb/official/2026/abw-terms.md";
    const ids = conflictDocIds({
      notes: [
        {
          kind: "unresolved_contradiction",
          citations: [
            {
              doc_id: id,
              title: "Terms",
              section: "Terms and conditions",
              source_url: "https://example",
              event_year: 2026,
              source_type: "official",
            },
          ],
        },
      ],
    });
    assert.equal(ids.has(id), true);
    assert.equal([...ids].some((s) => s.includes("s3://")), false);
  });
});
