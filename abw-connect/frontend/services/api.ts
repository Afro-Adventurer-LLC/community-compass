export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export type Citation = {
  doc_id: string;
  title: string;
  section: string;
  source_url: string;
  event_year: number;
  source_type: "official" | "alumni_experience" | string;
  retrieval_date?: string;
  evidence_span?: number[] | null;
  alumni_experience?: boolean;
};

export type Claim = {
  text: string;
  quote: string;
  citation: Citation;
  citations?: Citation[];
  alumni_experience?: boolean;
};

export type Note = {
  kind: string;
  text: string;
  quote?: string;
  citations?: Citation[];
};

export type PassageTrace = {
  id?: string;
  title?: string;
  section?: string;
  source_type?: string;
  event_year?: number;
  score?: number;
  primary?: boolean;
  suppressed?: boolean;
};

export type DroppedClaim = {
  text?: string;
  quote?: string;
  reason?: string;
  source?: string;
};

export type ChatResponse = {
  conversation_id: string;
  turn: number;
  question: string;
  interpreted_as?: string | null;
  turn_type?: string;
  kind: "answer" | "greeting" | "off_topic" | "task_request" | string;
  refused: boolean;
  refusal?: string | null;
  refusal_reason?: string | null;
  message?: string | null;
  suggestions?: string[];
  summary?: string | null;
  claims: Claim[];
  notes: Note[];
  outcome?: string | null;
  outcome_key?: string | null;
  generator?: string | null;
  generator_error?: string | null;
  latency_ms?: number;
  topic?: string | null;
  passages?: PassageTrace[];
  dropped?: DroppedClaim[];
};

export type HealthResponse = {
  status: string;
  mock: boolean;
  retriever: string;
  documents: number;
  default_generator: string;
  knowledge_base?: boolean;
};

export type UnansweredItem = {
  id: string;
  question: string;
  reason?: string;
  status?: string;
  source?: string;
  created_at?: string;
  event_year?: number;
  conversation_id?: string;
};

export type FeedbackItem = {
  id: string;
  conversation_id: string;
  turn: number;
  rating: "up" | "down";
  comment?: string | null;
  question?: string | null;
  created_at?: string;
};

async function parse<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data as T;
}

export async function health() {
  const res = await fetch(`${API_URL}/api/health`);
  return parse<HealthResponse>(res);
}

export async function sendChat(body: {
  question: string;
  conversation_id?: string | null;
  mode?: string;
  event_year?: number;
  include_alumni?: boolean;
}): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse<ChatResponse>(res);
}

export async function sendFeedback(body: {
  conversation_id: string;
  turn: number;
  rating: "up" | "down";
  question?: string;
}) {
  const res = await fetch(`${API_URL}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse<{ id: string; ok: boolean }>(res);
}

export async function flagUnanswered(body: {
  question: string;
  conversation_id?: string;
  turn?: number;
  reason?: string;
  event_year?: number;
}) {
  const res = await fetch(`${API_URL}/api/unanswered`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse<{ id: string; ok: boolean }>(res);
}

export async function listUnanswered() {
  const res = await fetch(`${API_URL}/api/advisor/unanswered`);
  return parse<{ items: UnansweredItem[] }>(res);
}

export async function listFeedback() {
  const res = await fetch(`${API_URL}/api/advisor/feedback`);
  return parse<{ items: FeedbackItem[] }>(res);
}
