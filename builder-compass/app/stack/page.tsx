"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CalendarDays,
  CalendarPlus,
  CircleAlert,
  Download,
  ExternalLink,
  Footprints,
  ListChecks,
  MapPin,
  ShieldCheck,
  X,
} from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { getSessions, getVenueGraph } from "@/lib/data";
import { useCompassStore, useHydrated } from "@/lib/store";
import { dateOf, dayLabel, dayLong, rangeLabel, weekdayShort } from "@/lib/format";
import {
  analyzeAll,
  findGaps,
  stackStats,
  summarizeDays,
  toBlocks,
  type Block,
} from "@/lib/schedule";
import { buildWalkLookup } from "@/lib/walkGraph";
import { blocksToIcs } from "@/lib/ics";
import { downloadFile } from "@/lib/download";
import { catalogDays } from "@/lib/planner";
import FeasibilityBadge, { ConflictPill } from "@/components/FeasibilityBadge";
import CustomItemForm from "@/components/CustomItemForm";
import GapRow from "@/components/GapRow";
import Button, { buttonClass } from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";
import Segmented from "@/components/ui/Segmented";

const OFFICIAL_SITE = "https://reinvent.awsevents.com/";

function Stat({
  label,
  value,
  sub,
  icon: Icon,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: typeof CalendarDays;
}) {
  return (
    <div className="rounded-xl border border-[var(--glass-ring)] bg-canvas/40 p-3">
      <div className="flex items-center gap-1.5 text-xs text-muted"><Icon size={14} className="text-brand-purple" aria-hidden />{label}</div>
      <div className="mt-2 font-mono text-xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

export default function StackPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [graph, setGraph] = useState<VenueGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<"schedule" | "reserve">("schedule");

  const hydrated = useHydrated();
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);
  const prefs = useCompassStore((s) => s.prefs);
  const removeFromPlan = useCompassStore((s) => s.removeFromPlan);
  const removeCustomItem = useCompassStore((s) => s.removeCustomItem);
  const setStatus = useCompassStore((s) => s.setStatus);

  useEffect(() => {
    Promise.all([getSessions(), getVenueGraph()])
      .then(([data, g]) => {
        setSessions(data);
        setGraph(g);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const lookup = useMemo(
    () => (graph ? buildWalkLookup(graph) : new Map<string, number>()),
    [graph]
  );
  const blocks = useMemo(
    () => toBlocks(plan, sessions, customItems),
    [plan, sessions, customItems]
  );
  const fits = useMemo(() => analyzeAll(blocks, lookup), [blocks, lookup]);
  const stats = useMemo(() => stackStats(blocks, fits), [blocks, fits]);

  const allDays = useMemo(() => {
    const days = new Set([...catalogDays(sessions), ...blocks.map((b) => dateOf(b.start))]);
    return Array.from(days).sort();
  }, [sessions, blocks]);
  const summaries = useMemo(
    () => summarizeDays(allDays, blocks, fits),
    [allDays, blocks, fits]
  );
  const gapByAfter = useMemo(
    () => new Map(findGaps(blocks, 60).map((g) => [g.after.key, g])),
    [blocks]
  );

  const byDay = useMemo(() => {
    const groups = new Map<string, Block[]>();
    for (const b of blocks) {
      const key = dateOf(b.start);
      groups.set(key, [...(groups.get(key) ?? []), b]);
    }
    return groups;
  }, [blocks]);

  const reservable = blocks.filter((b) => b.kind === "session" && !b.dropIn);
  const walkUp = blocks.filter((b) => b.kind === "session" && b.dropIn);
  const reservedCount = reservable.filter((b) => b.status === "reserved").length;

  function exportCalendar() {
    downloadFile("builder-compass-reinvent-2026.ics", blocksToIcs(blocks), "text/calendar");
  }

  if (failed) {
    return (
      <div className="space-y-6">
        <PageHeader title="Your stack" />
        <EmptyState
          icon={CircleAlert}
          tone="error"
          title="Your stack did not load"
          body="The catalog could not be loaded. Reload the page to try again."
        />
      </div>
    );
  }

  if (loading || !hydrated) {
    return (
      <div className="space-y-6" aria-busy="true">
        <PageHeader title="Your stack" subtitle="Loading your plan…" />
        <div className="h-28 animate-pulse rounded-2xl border border-border bg-canvas" />
        <div className="h-48 animate-pulse rounded-2xl border border-border bg-canvas" />
      </div>
    );
  }

  const issues = stats.conflictPairs + stats.notReachable;

  return (
    <div className="relative isolate space-y-6">
      <div className="glass-ambient" aria-hidden />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">
            Your re:Invent itinerary
          </p>
          <PageHeader
            title="Your stack"
            subtitle="Keep your week in order, spot travel issues, and finish your reservations."
          />
        </div>
        <Button variant="secondary" onClick={exportCalendar} disabled={blocks.length === 0}>
          <Download size={16} strokeWidth={1.75} aria-hidden />
          Export calendar
        </Button>
      </div>

      {blocks.length === 0 ? (
        <EmptyState
          icon={CalendarPlus}
          title="Your stack is empty"
          body="Add sessions from the catalog and Builder Compass will check the walk between each one. Or let the planner build a first draft."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link href="/plan" className={buttonClass("primary")}>
                Plan my week
              </Link>
              <Link href="/catalog" className={buttonClass("secondary")}>
                Browse the catalog
              </Link>
            </div>
          }
        />
      ) : (
        <>
          <Card glass className="p-4 sm:p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-semibold text-ink"><CalendarDays size={17} className="text-brand-purple" aria-hidden />Week at a glance</h2>
                <p className="mt-1 text-sm text-muted">{blocks.length} block{blocks.length === 1 ? "" : "s"} across {stats.days} day{stats.days === 1 ? "" : "s"}.</p>
              </div>
              {issues > 0 ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-error/10 px-2.5 py-1.5 text-xs font-semibold text-error-fg"><CircleAlert size={14} aria-hidden />{issues} item{issues === 1 ? "" : "s"} need{issues === 1 ? "s" : ""} attention</span>
              ) : stats.tight > 0 ? (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-warning/10 px-2.5 py-1.5 text-xs font-semibold text-warning-fg"><Footprints size={14} aria-hidden />{stats.tight} tight walk{stats.tight === 1 ? "" : "s"}, under 10 min to spare</span>
              ) : (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-success/10 px-2.5 py-1.5 text-xs font-semibold text-success-fg"><ShieldCheck size={14} aria-hidden />All clear</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-5">
              <Stat
                label="Sessions"
                value={String(stats.sessions)}
                sub={stats.custom ? `+ ${stats.custom} custom` : undefined}
                icon={ListChecks}
              />
              <Stat label="Time booked" value={`${stats.hours} h`} icon={CalendarDays} />
              <Stat
                label="Days"
                value={`${stats.days} of ${allDays.length}`}
                sub={
                  stats.busiestDay
                    ? `Busiest: ${weekdayShort(stats.busiestDay.day)}, ${stats.busiestDay.hours} h`
                    : undefined
                }
                icon={CalendarDays}
              />
              <Stat label="Walking" value={`${stats.walkMinutes} min`} sub="between venues" icon={MapPin} />
              <Stat
                label="Needs attention"
                value={String(issues)}
                sub={
                  issues > 0
                    ? `${stats.conflictPairs} overlap${stats.conflictPairs === 1 ? "" : "s"}, ${stats.notReachable} unreachable`
                    : stats.tight > 0
                      ? `+ ${stats.tight} tight walk${stats.tight === 1 ? "" : "s"} to watch`
                      : "no overlaps or tight walks"
                }
                icon={ShieldCheck}
              />
            </div>
          </Card>

          <nav aria-label="Week overview" className="grid grid-cols-3 gap-2 rounded-2xl border border-border bg-canvas/50 p-2 shadow-card sm:grid-cols-6">
            {summaries.map((d) => (
              <a
                key={d.day}
                href={`#day-${d.day}`}
                className={`rounded-xl border p-3 transition duration-200 hover:border-brand-purple/40 ${
                  d.blocks > 0
                    ? "border-border bg-canvas"
                    : "border-dashed border-border bg-transparent"
                }`}
              >
                <div className="flex items-center justify-between text-sm font-medium text-ink">
                  {weekdayShort(d.day)}
                  {d.issues > 0 ? (
                    <span
                      className="h-2 w-2 rounded-full bg-error"
                      role="img"
                      aria-label={`${d.issues} issue${d.issues === 1 ? "" : "s"}`}
                    />
                  ) : d.tight > 0 ? (
                    <span
                      className="h-2 w-2 rounded-full bg-warning"
                      role="img"
                      aria-label={`${d.tight} tight walk${d.tight === 1 ? "" : "s"}`}
                    />
                  ) : null}
                </div>
                <div className="font-mono text-xs text-muted">{dayLabel(d.day).split(", ")[1]}</div>
                <div className="mt-2 font-mono text-xs text-muted">
                  {d.blocks === 0 ? "Open" : `${d.blocks} · ${d.hours} h`}
                </div>
              </a>
            ))}
          </nav>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-ink">Manage your itinerary</h2>
              <p className="mt-0.5 text-xs text-muted">Review the schedule or complete reservations.</p>
            </div>
            <Segmented
              ariaLabel="Stack view"
              value={tab}
              onChange={setTab}
              options={[
                { value: "schedule", label: "Schedule" },
                { value: "reserve", label: `Reserve checklist (${reservedCount}/${reservable.length})` },
              ]}
            />
          </div>

          {tab === "schedule" ? (
            <div className="space-y-5">
              {Array.from(byDay.entries()).map(([day, dayBlocks]) => (
                <section key={day} id={`day-${day}`} className="scroll-mt-6 rounded-2xl border border-border bg-canvas/50 p-3 shadow-card sm:p-4">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-lg font-semibold text-ink">{dayLong(day)}</h2>
                    <span className="font-mono text-xs text-muted">{dayBlocks.length} block{dayBlocks.length === 1 ? "" : "s"}</span>
                  </div>
                  <ol className="space-y-3">
                    {dayBlocks.map((b) => {
                      const fit = fits.get(b.key);
                      const gap = gapByAfter.get(b.key);
                      const conflict = !!fit && fit.conflicts.length > 0;
                      return (
                        <Fragment key={b.key}>
                          {gap && (
                            <GapRow
                              gap={gap}
                              sessions={sessions}
                              blocks={blocks}
                              prefs={prefs}
                              lookup={lookup}
                            />
                          )}
                          <li
                            className={`rounded-xl border bg-canvas/80 p-4 shadow-card ${
                              conflict ? "border-error/40" : "border-border"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs">
                                  <span className="font-mono font-medium text-ink">
                                    {rangeLabel(b.start, b.end)}
                                  </span>
                                  {b.code ? (
                                    <span className="font-mono font-semibold text-brand-purple">
                                      {b.code}
                                    </span>
                                  ) : (
                                    <span className="rounded-md bg-surface px-1.5 py-0.5 font-medium text-muted">
                                      Custom
                                    </span>
                                  )}
                                  {b.dropIn && (
                                    <span className="rounded-md bg-surface px-1.5 py-0.5 font-medium text-muted">
                                      Drop-in
                                    </span>
                                  )}
                                  {b.status === "reserved" && (
                                    <span className="rounded-md bg-success/10 px-1.5 py-0.5 font-medium text-success-fg">
                                      Reserved
                                    </span>
                                  )}
                                  {conflict && fit && <ConflictPill others={fit.conflicts} />}
                                  {!conflict && fit?.arrival && fit.from && (
                                    <FeasibilityBadge
                                      result={fit.arrival}
                                      relativeTo={{ direction: "from", block: fit.from }}
                                    />
                                  )}
                                </div>
                                <div className="font-semibold leading-snug text-ink">
                                  {b.kind === "session" ? (
                                    <Link
                                      href={`/session/${encodeURIComponent(b.id)}`}
                                      className="transition duration-200 hover:text-brand-purple"
                                    >
                                      {b.title}
                                    </Link>
                                  ) : (
                                    b.title
                                  )}
                                </div>
                                {(b.venue || b.room) && (
                                  <div className="mt-0.5 text-sm text-muted">
                                    {[b.venue, b.room].filter(Boolean).join(" · ")}
                                  </div>
                                )}
                              </div>
                              <button
                                type="button"
                                onClick={() =>
                                  b.kind === "session"
                                    ? removeFromPlan(b.id)
                                    : removeCustomItem(b.id)
                                }
                                aria-label={`Remove ${b.title}`}
                                className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-lg text-muted transition duration-200 hover:bg-surface hover:text-ink"
                              >
                                <X size={18} strokeWidth={1.75} aria-hidden />
                              </button>
                            </div>
                          </li>
                        </Fragment>
                      );
                    })}
                  </ol>
                </section>
              ))}
            </div>
          ) : (
            <section className="space-y-6">
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="font-semibold text-ink">Reserve your seats</h2>
                    <p className="mt-1 max-w-xl text-sm text-muted">
                      Reservations are made on the official re:Invent site with
                      your AWS Builder ID. Builder Compass never asks for your
                      sign-in. Tick each session once you have a seat.
                    </p>
                  </div>
                  <a
                    href={OFFICIAL_SITE}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonClass("secondary")}
                  >
                    Open official site
                    <ExternalLink size={16} strokeWidth={1.75} aria-hidden />
                  </a>
                </div>
                <div className="mt-4">
                  <div className="mb-1.5 flex justify-between font-mono text-xs text-muted">
                    <span>
                      {reservedCount} of {reservable.length} reserved
                    </span>
                    <span>
                      {reservable.length === 0
                        ? "0%"
                        : `${Math.round((reservedCount / reservable.length) * 100)}%`}
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-label="Reservation progress"
                    aria-valuemin={0}
                    aria-valuemax={reservable.length}
                    aria-valuenow={reservedCount}
                    className="h-2 overflow-hidden rounded-full bg-surface"
                  >
                    <div
                      className="h-full rounded-full bg-success transition-all duration-200"
                      style={{
                        width: `${reservable.length ? (reservedCount / reservable.length) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              </Card>

              {reservable.length === 0 ? (
                <p className="text-sm text-muted">
                  None of the sessions in your stack need a reservation.
                </p>
              ) : (
                Array.from(
                  reservable.reduce((map, b) => {
                    const d = dateOf(b.start);
                    map.set(d, [...(map.get(d) ?? []), b]);
                    return map;
                  }, new Map<string, Block[]>())
                ).map(([day, list]) => (
                  <div key={day}>
                    <h3 className="mb-2 text-sm font-medium text-muted">{dayLong(day)}</h3>
                    <ul className="space-y-2">
                      {list.map((b) => {
                        const reserved = b.status === "reserved";
                        return (
                          <li key={b.key}>
                            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-canvas p-3 transition duration-200 hover:border-border-strong">
                              <input
                                type="checkbox"
                                checked={reserved}
                                onChange={() =>
                                  setStatus(b.id, reserved ? "planned" : "reserved")
                                }
                                className="mt-1 h-4 w-4 cursor-pointer accent-brand-purple"
                              />
                              <span className="min-w-0 flex-1">
                                <span className="block font-mono text-xs text-muted">
                                  {rangeLabel(b.start, b.end)} · {b.code} · {b.venue}
                                </span>
                                <span
                                  className={`block text-sm font-semibold ${
                                    reserved ? "text-muted line-through" : "text-ink"
                                  }`}
                                >
                                  {b.title}
                                </span>
                              </span>
                              {reserved && (
                                <span className="rounded-md bg-success/10 px-1.5 py-0.5 text-xs font-medium text-success-fg">
                                  Reserved
                                </span>
                              )}
                            </label>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))
              )}

              {walkUp.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-medium text-muted">
                    Walk-up, no reservation needed
                  </h3>
                  <ul className="space-y-2">
                    {walkUp.map((b) => (
                      <li
                        key={b.key}
                        className="rounded-xl border border-border bg-canvas p-3 text-sm"
                      >
                        <span className="font-mono text-xs text-muted">
                          {dayLabel(b.start)} · {rangeLabel(b.start, b.end)} · {b.code}
                        </span>
                        <span className="block font-semibold text-ink">{b.title}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </>
      )}

      <CustomItemForm />
    </div>
  );
}
