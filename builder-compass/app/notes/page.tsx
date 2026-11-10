"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Copy,
  Download,
  ListChecks,
  MapPin,
  NotebookPen,
  Star,
} from "lucide-react";
import type { PlanItem, Session } from "@/types";
import { getSessions } from "@/lib/data";
import { useCompassStore, useHydrated } from "@/lib/store";
import { dateOf, dayLabel, rangeLabel } from "@/lib/format";
import { toBlocks } from "@/lib/schedule";
import { reportToMarkdown, scheduleToMarkdown } from "@/lib/markdown";
import { blocksToIcs } from "@/lib/ics";
import { copyText, downloadFile } from "@/lib/download";
import RatingForm from "@/components/RatingForm";
import Button, { buttonClass, inputClass } from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";
import Segmented from "@/components/ui/Segmented";

type ExportTab = "report" | "schedule";
type Filter = "all" | "todo" | "done";

// A session counts as reviewed once you have captured anything about it.
function isReviewed(item?: PlanItem): boolean {
  if (!item) return false;
  const r = item.rating;
  return (
    (r?.value ?? 0) > 0 ||
    r?.wouldRecommend !== undefined ||
    !!r?.takeaway?.trim() ||
    !!r?.actionItems?.trim() ||
    !!item.note?.text?.trim()
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-[var(--glass-ring)] bg-canvas/50 px-4 py-3">
      <p className="font-mono text-[10px] font-semibold uppercase tracking-[.12em] text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export default function NotesPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<ExportTab>("report");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const hydrated = useHydrated();
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);
  const setNote = useCompassStore((s) => s.setNote);
  const archive = useCompassStore((s) => s.archive);
  // Sessions removed from the stack whose notes and ratings were kept.
  const archived = useMemo(() => Object.values(archive), [archive]);

  useEffect(() => {
    getSessions()
      .then(setSessions)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(t);
  }, [copied]);

  const blocks = useMemo(() => toBlocks(plan, sessions, customItems), [plan, sessions, customItems]);
  const planById = useMemo(() => new Map(plan.map((p) => [p.sessionId, p])), [plan]);
  // Sessions in the order you attend them.
  const entries = useMemo(
    () => blocks.filter((b) => b.kind === "session" && b.session).map((b) => b.session as Session),
    [blocks]
  );

  const stats = useMemo(() => {
    const reviewed = entries.filter((s) => isReviewed(planById.get(s.id))).length;
    const ratings = entries.map((s) => planById.get(s.id)?.rating?.value ?? 0).filter((v) => v > 0);
    const average = ratings.length ? ratings.reduce((a, b) => a + b, 0) / ratings.length : null;
    const actions = entries.filter((s) => planById.get(s.id)?.rating?.actionItems?.trim()).length;
    const recommended = entries.filter((s) => planById.get(s.id)?.rating?.wouldRecommend === true).length;
    return { reviewed, average, actions, recommended };
  }, [entries, planById]);

  const visible = useMemo(
    () =>
      entries.filter((s) => {
        const done = isReviewed(planById.get(s.id));
        return filter === "all" || (filter === "done" ? done : !done);
      }),
    [entries, planById, filter]
  );
  const days = useMemo(() => {
    const groups = new Map<string, Session[]>();
    visible.forEach((s) => groups.set(dateOf(s.start), [...(groups.get(dateOf(s.start)) ?? []), s]));
    return Array.from(groups.entries());
  }, [visible]);

  const current = entries.find((s) => s.id === selectedId) ?? visible[0] ?? entries[0];
  const currentIndex = current ? entries.findIndex((s) => s.id === current.id) : -1;
  const currentItem = current ? planById.get(current.id) : undefined;

  const markdown = useMemo(
    () => (tab === "schedule"
        ? scheduleToMarkdown(blocks, plan)
        : reportToMarkdown([...plan, ...archived], sessions)),
    [tab, blocks, plan, archived, sessions]
  );

  if (failed) {
    return (
      <div className="space-y-6">
        <PageHeader title="Notes" />
        <EmptyState icon={CircleAlert} tone="error" title="Your notes did not load" body="The catalog could not be loaded. Reload the page to try again." />
      </div>
    );
  }

  if (loading || !hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <PageHeader title="Notes" subtitle="Loading your sessions…" />
        <div className="h-48 animate-pulse rounded-2xl border border-border bg-canvas" />
      </div>
    );
  }

  async function copyMarkdown() {
    setCopied(await copyText(markdown));
  }

  const progress = entries.length ? Math.round((stats.reviewed / entries.length) * 100) : 0;

  return (
    <div className="relative isolate space-y-6">
      <div className="glass-ambient" aria-hidden />
      <div>
        <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">Capture re:Invent</p>
        <PageHeader
          title="Notes"
          subtitle="Rate sessions, jot what you learned, and turn it into a trip report for your team."
        />
      </div>

      {entries.length === 0 ? (
        <Card glass>
          <EmptyState
            icon={NotebookPen}
            title="Nothing to review yet"
            body="Add sessions to your Stack and they will appear here, in the order you attend them."
            action={<Link href="/catalog" className={buttonClass("primary")}>Browse the catalog</Link>}
          />
        </Card>
      ) : (
        <>
          <Card glass className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-brand-purple">Your progress</p>
                <p className="mt-1 text-lg font-semibold text-ink">
                  {stats.reviewed} of {entries.length} session{entries.length === 1 ? "" : "s"} reviewed
                </p>
              </div>
              <span className="font-mono text-sm font-semibold text-muted">{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-surface" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Sessions reviewed">
              <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${progress}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Avg rating" value={stats.average ? stats.average.toFixed(1) : "–"} hint={stats.average ? "out of 5" : "Not rated yet"} />
              <Stat label="Recommended" value={String(stats.recommended)} hint="would tell a teammate" />
              <Stat label="Action items" value={String(stats.actions)} hint="to follow up" />
              <Stat label="Sessions" value={String(entries.length)} hint="in your Stack" />
            </div>
          </Card>

          <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)] lg:items-start">
            <Card glass className="overflow-hidden p-0">
              <div className="border-b border-[var(--glass-ring)] p-3">
                <Segmented
                  ariaLabel="Filter sessions"
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: "all", label: `All ${entries.length}` },
                    { value: "todo", label: `To review ${entries.length - stats.reviewed}` },
                    { value: "done", label: `Done ${stats.reviewed}` },
                  ]}
                />
              </div>
              <div className="max-h-[560px] overflow-y-auto">
                {days.length === 0 ? (
                  <p className="p-6 text-center text-sm text-muted">
                    {filter === "todo" ? "Everything is reviewed. Nice work." : "Nothing reviewed yet."}
                  </p>
                ) : (
                  days.map(([day, list]) => (
                    <section key={day} aria-label={dayLabel(day)}>
                      <h2 className="sticky top-0 z-10 border-b border-[var(--glass-ring)] bg-canvas/85 px-4 py-2 font-mono text-[11px] font-semibold uppercase tracking-[.12em] text-muted backdrop-blur">{dayLabel(day)}</h2>
                      <ul>
                        {list.map((s) => {
                          const item = planById.get(s.id);
                          const active = current?.id === s.id;
                          const done = isReviewed(item);
                          const stars = item?.rating?.value ?? 0;
                          return (
                            <li key={s.id}>
                              <button
                                type="button"
                                onClick={() => setSelectedId(s.id)}
                                aria-current={active ? "true" : undefined}
                                className={`flex w-full gap-3 border-l-2 px-4 py-3 text-left transition duration-200 ${
                                  active ? "border-brand-purple bg-brand-tint" : "border-transparent hover:bg-surface"
                                }`}
                              >
                                <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${done ? "border-success bg-success text-white dark:text-code" : "border-border-strong text-transparent"}`} aria-hidden>
                                  <Check size={12} strokeWidth={3} />
                                </span>
                                <span className="min-w-0 flex-1">
                                  <span className="flex items-center justify-between gap-2 font-mono text-[11px] text-muted">
                                    <span>{rangeLabel(s.start, s.end)}</span>
                                    <span className={active ? "font-semibold text-brand-purple" : ""}>{s.code}</span>
                                  </span>
                                  <span className="mt-0.5 line-clamp-2 block text-sm font-semibold leading-snug text-ink">{s.title}</span>
                                  {(stars > 0 || item?.note?.text?.trim() || item?.rating?.actionItems?.trim()) && (
                                    <span className="mt-1.5 flex items-center gap-2.5 text-xs text-muted">
                                      {stars > 0 && <span className="inline-flex items-center gap-1 font-mono"><Star size={12} className="fill-brand-orange text-brand-orange" aria-hidden />{stars}</span>}
                                      {item?.note?.text?.trim() && <span className="inline-flex items-center gap-1"><NotebookPen size={12} aria-hidden />Note</span>}
                                      {item?.rating?.actionItems?.trim() && <span className="inline-flex items-center gap-1"><ListChecks size={12} aria-hidden />Action</span>}
                                    </span>
                                  )}
                                </span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  ))
                )}
              </div>
            </Card>

            {current && (
              <Card glass className="space-y-5 lg:sticky lg:top-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs">
                      <span className="font-semibold text-brand-purple">{current.code}</span>
                      <span className="text-muted">{dayLabel(current.start)} · {rangeLabel(current.start, current.end)}</span>
                    </div>
                    <h2 className="mt-1.5 text-xl font-semibold leading-snug tracking-tight text-ink">{current.title}</h2>
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                      <span className="inline-flex items-center gap-1"><MapPin size={14} aria-hidden />{[current.venue, current.room].filter(Boolean).join(" · ")}</span>
                      <Link href={`/session/${encodeURIComponent(current.id)}`} className="inline-flex items-center gap-0.5 font-semibold text-brand-purple hover:underline">Session details<ArrowUpRight size={13} aria-hidden /></Link>
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button type="button" aria-label="Previous session" disabled={currentIndex <= 0} onClick={() => setSelectedId(entries[currentIndex - 1].id)} className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border-strong bg-canvas text-ink transition duration-200 hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"><ChevronLeft size={18} aria-hidden /></button>
                    <button type="button" aria-label="Next session" disabled={currentIndex >= entries.length - 1} onClick={() => setSelectedId(entries[currentIndex + 1].id)} className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg border border-border-strong bg-canvas text-ink transition duration-200 hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40"><ChevronRight size={18} aria-hidden /></button>
                  </div>
                </div>

                <RatingForm key={current.id} sessionId={current.id} title={current.title} rating={currentItem?.rating} />

                <label className="block text-sm">
                  <span className="mb-1.5 block font-medium text-ink">Notes</span>
                  <textarea
                    value={currentItem?.note?.text ?? ""}
                    onChange={(e) => setNote(current.id, e.target.value)}
                    rows={5}
                    placeholder="Anything worth remembering from the session"
                    className={inputClass}
                  />
                </label>
                <p className="flex items-center gap-1.5 text-xs text-muted"><Check size={12} aria-hidden />Saves automatically in this browser.</p>
              </Card>
            )}
          </div>
        </>
      )}

      <Card glass className="overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--glass-ring)] px-5 py-4">
          <div>
            <h2 className="font-semibold text-ink">Export</h2>
            <p className="mt-1 text-sm text-muted">Share a trip report with your team or take your schedule to your calendar.</p>
          </div>
          <Segmented
            ariaLabel="Export type"
            value={tab}
            onChange={setTab}
            options={[
              { value: "report", label: "Trip report" },
              { value: "schedule", label: "Schedule" },
            ]}
          />
        </div>
        <div className="space-y-3 p-5">
          {tab === "report" && archived.length > 0 && (
            <p className="text-xs text-muted">
              Includes notes from {archived.length} session{archived.length === 1 ? "" : "s"} you
              removed from your stack. Add {archived.length === 1 ? "it" : "one"} back to edit
              those notes; they come back with it.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={copyMarkdown}>
              {copied ? <ClipboardCheck size={16} strokeWidth={1.75} aria-hidden /> : <Copy size={16} strokeWidth={1.75} aria-hidden />}
              {copied ? "Copied" : "Copy"}
            </Button>
            {tab === "schedule" && (
              <Button
                variant="secondary"
                disabled={blocks.length === 0}
                onClick={() => downloadFile("builder-compass-reinvent-2026.ics", blocksToIcs(blocks), "text/calendar")}
              >
                <Download size={16} strokeWidth={1.75} aria-hidden />
                Calendar (.ics)
              </Button>
            )}
            <Button onClick={() => downloadFile(tab === "schedule" ? "reinvent-schedule.md" : "reinvent-trip-report.md", markdown, "text/markdown")}>
              <Download size={16} strokeWidth={2} aria-hidden />
              Download Markdown
            </Button>
          </div>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-code p-4 font-mono text-xs leading-relaxed text-white/90" aria-label="Markdown preview">
            {markdown}
          </pre>
        </div>
      </Card>
    </div>
  );
}
