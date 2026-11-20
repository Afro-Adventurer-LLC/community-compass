"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { health, sendChat, type ChatResponse } from "@/services/abwApi";
import {
  chatRequestMode,
  loadGeneratorMode,
  saveGeneratorMode,
  type GeneratorMode,
} from "@/lib/abw/generatorMode";
import { formatHealthStatus } from "@/lib/abw/presentAnswer";
import MessageBubble from "./MessageBubble";

type Row =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; answer?: ChatResponse; loading?: boolean; error?: string };

const STARTERS = [
  "Who is eligible for the All Builders Welcome Grant?",
  "What does the All Builders Welcome Grant cover?",
  "When is the deadline to request accessibility accommodations?",
  "How much time should I leave between re:Invent venues?",
];

export default function Chat({ initialQuestion }: { initialQuestion?: string | null } = {}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [input, setInput] = useState("");
  const [cid, setCid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<GeneratorMode>("llm");
  const [year, setYear] = useState(2026);
  const [status, setStatus] = useState("Checking backend…");
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const autoAsked = useRef(false);

  useEffect(() => {
    health()
      .then((h) => setStatus(formatHealthStatus(h)))
      .catch(() => setStatus("ABW API unreachable"));
  }, []);

  useEffect(() => {
    setMode(loadGeneratorMode(window.localStorage));
  }, []);

  useEffect(() => {
    if (rows.length) bottom.current?.scrollIntoView({ block: "end" });
  }, [rows]);

  // Opened from "Ask about this session" (or any ?q= link): send it once.
  useEffect(() => {
    const q = initialQuestion?.trim();
    if (!q || autoAsked.current) return;
    autoAsked.current = true;
    void ask(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  function newChat() {
    setCid(null);
    setRows([]);
    setErrorBanner(null);
  }

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setErrorBanner(null);
    setInput("");
    const userId = `u-${Date.now()}`;
    const pendingId = `a-${Date.now()}`;
    setRows((r) => [
      ...r,
      { id: userId, role: "user", text: q },
      { id: pendingId, role: "assistant", loading: true },
    ]);
    try {
      const a = await sendChat({
        question: q,
        conversation_id: cid,
        mode: chatRequestMode(mode),
        event_year: year,
        include_alumni: true,
      });
      setCid(a.conversation_id);
      setRows((r) => r.map((row) => (row.id === pendingId ? { id: pendingId, role: "assistant", answer: a } : row)));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Request failed";
      setErrorBanner(msg);
      setRows((r) =>
        r.map((row) => (row.id === pendingId ? { id: pendingId, role: "assistant", error: msg } : row)),
      );
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void ask(input);
  }

  const empty = rows.length === 0;

  return (
    <div className="flex min-h-[calc(100vh-16rem)] flex-col overflow-hidden rounded-2xl border border-border bg-canvas shadow-card">
      <div className="border-b border-border bg-canvas">
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <label className="text-xs font-medium text-muted">
            Generator
            <select
              className="ml-2 rounded-lg border border-border-strong bg-canvas px-2 py-1 text-sm text-ink focus:border-brand-purple"
              value={mode}
              onChange={(e) => {
                const next = e.target.value as GeneratorMode;
                setMode(next);
                saveGeneratorMode(next, window.localStorage);
              }}
            >
              <option value="llm">LLM (Bedrock)</option>
              <option value="auto">Auto</option>
              <option value="extractive">Extractive</option>
            </select>
          </label>
          <label className="text-xs font-medium text-muted">
            Event year
            <select
              className="ml-2 rounded-lg border border-border-strong bg-canvas px-2 py-1 text-sm text-ink focus:border-brand-purple"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            >
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
            </select>
          </label>
          <span className="font-mono text-xs text-muted">{status}</span>
          <button
            type="button"
            className="ml-auto rounded-lg border border-border-strong bg-canvas px-3 py-1 text-sm font-semibold text-ink transition duration-200 hover:bg-surface"
            onClick={newChat}
          >
            New chat
          </button>
        </div>
      </div>

      <div className="flex w-full flex-1 flex-col px-4 py-4 sm:px-6">
        {errorBanner ? (
          <div className="mb-3 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error-fg">
            {errorBanner}
          </div>
        ) : null}

        {empty ? (
          <div className="flex flex-1 flex-col items-start justify-center gap-4 py-10">
            <div>
              <h2 className="text-xl font-bold tracking-tight text-ink">Ask about the ABW grant or re:Invent</h2>
              <p className="mt-1 max-w-xl text-sm text-muted">
                Answers are cited from official pages. Alumni write-ups are labeled as personal experience and never
                override official guidance. If official sources disagree, both values are shown.
              </p>
            </div>
            <div className="grid w-full gap-2 sm:grid-cols-2">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="rounded-xl border border-border bg-canvas px-3 py-3 text-left text-sm text-ink transition duration-200 hover:border-brand-purple hover:bg-brand-tint"
                  onClick={() => void ask(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col gap-3 pb-6">
            {rows.map((row) =>
              row.role === "user" ? (
                <MessageBubble key={row.id} role="user" text={row.text} />
              ) : (
                <MessageBubble
                  key={row.id}
                  role="assistant"
                  answer={row.answer}
                  loading={row.loading}
                  error={row.error}
                  onSuggestion={(q) => void ask(q)}
                />
              ),
            )}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="sticky bottom-0 border-t border-border bg-canvas/90 backdrop-blur">
        <div className="flex gap-2 px-4 py-3 sm:px-6">
          <textarea
            className="min-h-[46px] flex-1 resize-none rounded-xl border border-border-strong bg-canvas px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-brand-purple focus:outline-none"
            rows={1}
            placeholder="Ask a question, then follow up (e.g. “how many days?”). Enter to send."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(input);
              }
            }}
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-white transition duration-200 hover:opacity-90 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
