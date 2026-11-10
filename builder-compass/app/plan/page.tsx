"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { CalendarDays, Check, CircleAlert, ListChecks, Sparkles } from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { getSessions, getVenueGraph } from "@/lib/data";
import { useCompassStore, useHydrated } from "@/lib/store";
import { dayLong } from "@/lib/format";
import { activeDays, catalogDays, planWeek, type PlannedDay } from "@/lib/planner";
import { toBlocks } from "@/lib/schedule";
import { buildWalkLookup } from "@/lib/walkGraph";
import ProfilePanel from "@/components/plan/ProfilePanel";
import AiBridge from "@/components/plan/AiBridge";
import SessionRow from "@/components/SessionRow";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";

interface Proposal {
  days: PlannedDay[];
  key: string; // snapshot of the profile this draft was made from
}

export default function PlanPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [graph, setGraph] = useState<VenueGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [addedCount, setAddedCount] = useState<number | null>(null);

  const hydrated = useHydrated();
  const prefs = useCompassStore((s) => s.prefs);
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);
  const addManyToPlan = useCompassStore((s) => s.addManyToPlan);

  useEffect(() => {
    Promise.all([getSessions(), getVenueGraph()])
      .then(([data, g]) => {
        setSessions(data);
        setGraph(g);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const allDays = useMemo(() => catalogDays(sessions), [sessions]);
  const days = useMemo(() => activeDays(allDays, prefs), [allDays, prefs]);
  const lookup = useMemo(
    () => (graph ? buildWalkLookup(graph) : new Map<string, number>()),
    [graph]
  );
  const blocks = useMemo(
    () => toBlocks(plan, sessions, customItems),
    [plan, sessions, customItems]
  );
  const plannedIds = useMemo(() => new Set(plan.map((p) => p.sessionId)), [plan]);

  // Everything that changes the draft (the goal text only affects the AI prompt).
  const prefsKey = JSON.stringify([
    prefs.interests,
    prefs.depth,
    prefs.role,
    prefs.days,
    prefs.includeEvents,
    prefs.maxPerDay,
  ]);

  const generate = useCallback(() => {
    setProposal({
      days: planWeek(sessions, blocks, prefs, lookup, days),
      key: prefsKey,
    });
    setAddedCount(null);
  }, [sessions, blocks, prefs, lookup, days, prefsKey]);

  // First draft appears automatically once saved data and the catalog are ready.
  useEffect(() => {
    if (hydrated && !loading && !failed && !proposal) generate();
  }, [hydrated, loading, failed, proposal, generate]);

  const stale = !!proposal && proposal.key !== prefsKey;
  const allPicks = proposal?.days.flatMap((d) => d.picks) ?? [];
  const toAdd = allPicks.filter((p) => !plannedIds.has(p.session.id));

  function addPicks(ids: string[]) {
    const fresh = ids.filter((id) => !plannedIds.has(id));
    addManyToPlan(fresh);
    setAddedCount(fresh.length);
  }

  if (failed) {
    return (
      <div className="space-y-6">
        <PageHeader title="Plan my week" />
        <EmptyState
          icon={CircleAlert}
          tone="error"
          title="The planner did not load"
          body="The catalog could not be loaded. Reload the page to try again."
        />
      </div>
    );
  }

  if (loading || !hydrated || !graph) {
    return (
      <div className="space-y-6" aria-busy="true">
        <PageHeader title="Plan my week" subtitle="Loading the catalog…" />
        <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
          <div className="h-96 animate-pulse rounded-2xl border border-border bg-canvas" />
          <div className="h-96 animate-pulse rounded-2xl border border-border bg-canvas" />
        </div>
      </div>
    );
  }

  const plannedDays = proposal?.days.filter((d) => d.picks.length > 0).length ?? 0;

  return (
    <div className="relative isolate space-y-6">
      <div className="glass-ambient" aria-hidden />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">
            Your re:Invent week
          </p>
          <PageHeader
            title="Plan with confidence"
            subtitle="A tailored draft that avoids overlaps and accounts for the walk between venues."
          />
        </div>
        <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-canvas/70 text-center shadow-card">
          <div className="border-r border-border px-4 py-2.5">
            <p className="font-mono text-lg font-semibold leading-none text-ink">{allPicks.length}</p>
            <p className="mt-1 text-xs text-muted">suggested</p>
          </div>
          <div className="px-4 py-2.5">
            <p className="font-mono text-lg font-semibold leading-none text-ink">{plannedDays}</p>
            <p className="mt-1 text-xs text-muted">days planned</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
        <div className="order-2 lg:order-1">
          <ProfilePanel sessions={sessions} days={allDays} />
        </div>

        <div className="order-1 space-y-6 lg:order-2">
          <Card glass className="overflow-hidden p-0">
            <div className="border-b border-[var(--glass-ring)] px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-semibold text-ink">
                  <Sparkles size={16} strokeWidth={1.75} className="text-brand-purple" aria-hidden />
                  Your draft week
                </h2>
                <p className="mt-1 font-mono text-sm text-muted">
                  {allPicks.length} suggested across{" "}
                  {proposal?.days.filter((d) => d.picks.length > 0).length ?? 0} of{" "}
                  {days.length} days
                </p>
              </div>
                <div className="flex flex-wrap gap-2">
                <Button variant="secondary" onClick={generate}>
                  Plan again
                </Button>
                <Button
                  onClick={() => addPicks(toAdd.map((p) => p.session.id))}
                  disabled={toAdd.length === 0}
                >
                  Add all {toAdd.length > 0 ? `(${toAdd.length})` : ""}
                </Button>
                </div>
              </div>
            </div>

            <div className="p-4 sm:p-5">
              <div className="mb-5 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--glass-ring)] bg-canvas/30 px-3 py-2.5 text-xs text-muted">
                <span className="inline-flex items-center gap-1.5"><CalendarDays size={14} className="text-brand-purple" aria-hidden />{days.length} days in scope</span>
                <span className="hidden h-3 border-l border-border sm:block" aria-hidden />
                <span className="inline-flex items-center gap-1.5"><ListChecks size={14} className="text-brand-purple" aria-hidden />Add individual days or the full draft</span>
              </div>

            {stale && (
              <p role="status" className="rounded-xl bg-warning/10 p-3 text-sm text-warning-fg">
                Your profile changed. Choose Plan again to refresh this draft.
              </p>
            )}

            {addedCount !== null && (
              <p
                role="status"
                className="flex items-center gap-2 rounded-xl bg-success/10 p-3 text-sm text-success-fg"
              >
                <Check size={16} strokeWidth={2} aria-hidden />
                Added {addedCount} session{addedCount === 1 ? "" : "s"} to your stack.{" "}
                <Link href="/stack" className="font-semibold underline">
                  View your stack
                </Link>
              </p>
            )}

            <div className="space-y-5">
              {proposal?.days.map((d) => {
                const dayIds = d.picks
                  .map((p) => p.session.id)
                  .filter((id) => !plannedIds.has(id));
                return (
                  <section key={d.day} className="rounded-2xl border border-[var(--glass-ring)] bg-canvas/30 p-3 sm:p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <h3 className="flex flex-wrap items-center gap-2 font-semibold text-ink">
                          {dayLong(d.day)}
                          {d.theme && (
                            <span className="rounded-md bg-brand-tint px-2 py-0.5 text-xs font-medium text-brand-purple">
                              {d.theme}
                            </span>
                          )}
                        </h3>
                        <p className="mt-1 text-xs text-muted">{d.picks.length > 0 ? `${d.picks.length} recommended sessions` : "No recommendations yet"}</p>
                      </div>
                      {d.picks.length > 0 && (
                        <Button
                          variant="secondary"
                          disabled={dayIds.length === 0}
                          onClick={() => addPicks(dayIds)}
                        >
                          {dayIds.length === 0 ? "Added" : `Add day (${dayIds.length})`}
                        </Button>
                      )}
                    </div>
                    {d.picks.length > 0 ? (
                      <ul className="space-y-2">
                        {d.picks.map((p) => (
                          <SessionRow
                            key={p.session.id}
                            session={p.session}
                            fit={p.fit}
                            reasons={p.reasons}
                          />
                        ))}
                      </ul>
                    ) : (
                      <p className="rounded-xl border border-dashed border-border-strong p-4 text-sm text-muted">
                        {d.full
                          ? `This day is full: you already have ${d.plannedToday} session${d.plannedToday === 1 ? "" : "s"} in your stack. Raise “Sessions per day” to add more.`
                          : "No reachable matches for this day. Add interests, raise the daily limit, or include events."}
                      </p>
                    )}
                  </section>
                );
              })}
            </div>
            </div>
          </Card>

          <AiBridge
            sessions={sessions}
            graph={graph}
            days={days}
            blocks={blocks}
            lookup={lookup}
          />
        </div>
      </div>
    </div>
  );
}
