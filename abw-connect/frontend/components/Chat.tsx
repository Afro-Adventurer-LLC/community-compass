"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { health, sendChat, type ChatResponse } from "@/services/api";
import {
  chatRequestMode,
  loadGeneratorMode,
  saveGeneratorMode,
  type GeneratorMode,
} from "@/lib/generatorMode";
import { formatHealthStatus } from "@/lib/presentAnswer";
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

export default function Chat() {
  const [rows, setRows] = useState<Row[]>([]);
  const [input, setInput] = useState("");
  const [cid, setCid] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<GeneratorMode>("llm");
  const [year, setYear] = useState(2026);
  const [status, setStatus] = useState("Checking backend…");
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    health()
      .then((h) => setStatus(formatHealthStatus(h)))
      .catch(() => setStatus("Backend unreachable — start FastAPI on :8000"));
  }, []);

  useEffect(() => {
    setMode(loadGeneratorMode(window.localStorage));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [rows]);

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
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col">
      <div className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-3 px-4 py-3">
          <label className="text-xs font-medium text-ink-500">
            Generator
            <select
              className="ml-2 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm text-ink"
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
          <label className="text-xs font-medium text-ink-500">
            Event year
            <select
              className="ml-2 rounded-md border border-slate-200 bg-white px-2 py-1 text-sm text-ink"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            >
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
            </select>
          </label>
          <span className="text-xs text-slate-500">{status}</span>
          <button
            type="button"
            className="ml-auto rounded-md border border-slate-200 px-3 py-1 text-sm hover:bg-slate-50"
            onClick={newChat}
          >
            New chat
          </button>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 py-4">
        {errorBanner ? (
          <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {errorBanner}
          </div>
        ) : null}

        {empty ? (
          <div className="flex flex-1 flex-col items-start justify-center gap-4 py-10">
            <div>
              <h2 className="text-xl font-semibold">Ask about the ABW grant or re:Invent</h2>
              <p className="mt-1 max-w-xl text-sm text-ink-500">
                Answers are cited from official pages. Alumni write-ups are labeled as personal experience and never
                override official guidance. If official sources disagree, both values are shown.
              </p>
            </div>
            <div className="grid w-full gap-2 sm:grid-cols-2">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-left text-sm hover:border-accent"
                  onClick={() => void ask(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-1 flex-col gap-3 pb-28">
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

      <form onSubmit={onSubmit} className="sticky bottom-0 border-t border-slate-200 bg-slate-50/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl gap-2 px-4 py-3">
          <textarea
            className="min-h-[46px] flex-1 resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
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
            className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-600 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
