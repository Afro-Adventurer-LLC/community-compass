"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Plus } from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { getSessions, getVenueGraph } from "@/lib/data";
import { useCompassStore, useHydrated } from "@/lib/store";
import {
  dayLong,
  durationLabel,
  levelLabel,
  minutesBetween,
  rangeLabel,
  timeOf,
} from "@/lib/format";
import { fitCheck, sessionToBlock, toBlocks } from "@/lib/schedule";
import { buildWalkLookup } from "@/lib/walkGraph";
import Button, { inputClass } from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import FeasibilityBadge, { otherLabel } from "@/components/FeasibilityBadge";
import SessionRow from "@/components/SessionRow";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 py-3 text-sm">
      <dt className="w-24 shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </div>
  );
}

// The session itself arrives from the server, so the page content is in the
// initial HTML. Only the "fit with your stack" check needs the full catalog
// (to resolve the other sessions in your plan), and it loads that lazily.
export default function SessionDetail({
  session,
  related,
}: {
  session: Session;
  related: Session[];
}) {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [graph, setGraph] = useState<VenueGraph | null>(null);
  const [fitFailed, setFitFailed] = useState(false);

  const hydrated = useHydrated();
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);
  const addToPlan = useCompassStore((s) => s.addToPlan);
  const removeFromPlan = useCompassStore((s) => s.removeFromPlan);
  const setNote = useCompassStore((s) => s.setNote);

  useEffect(() => {
    Promise.all([getSessions(), getVenueGraph()])
      .then(([data, g]) => {
        setSessions(data);
        setGraph(g);
      })
      .catch(() => setFitFailed(true));
  }, []);

  const planItem = plan.find((p) => p.sessionId === session.id);
  const lookup = useMemo(
    () => (graph ? buildWalkLookup(graph) : new Map<string, number>()),
    [graph]
  );
  const fit = useMemo(() => {
    if (!sessions) return null;
    const blocks = toBlocks(plan, sessions, customItems);
    return fitCheck(sessionToBlock(session), blocks, lookup);
  }, [session, sessions, plan, customItems, lookup]);

  const minutes = minutesBetween(session.start, session.end);
  const planned = !!planItem;

  return (
    <div className="space-y-6">
      <Link
        href="/catalog"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted transition duration-200 hover:text-ink"
      >
        <ArrowLeft size={16} strokeWidth={1.75} aria-hidden />
        Catalog
      </Link>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* Main column */}
        <div className="space-y-6">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-mono text-sm font-semibold text-brand-purple">
                {session.code}
              </span>
              <span
                className={`rounded-md px-2 py-1 font-semibold ${
                  session.level === 0
                    ? "bg-surface text-muted"
                    : "bg-brand-tint text-brand-purple"
                }`}
              >
                {levelLabel(session.level)}
              </span>
              <span className="rounded-md bg-surface px-2 py-1 text-muted">
                {session.type}
              </span>
              <span className="rounded-md bg-surface px-2 py-1 text-muted">
                {session.track}
              </span>
            </div>
            <h1 className="text-2xl font-bold leading-snug tracking-tight text-ink md:text-3xl">
              {session.title}
            </h1>
          </div>

          <Card>
            <h2 className="mb-2 font-semibold text-ink">About this session</h2>
            <p className="whitespace-pre-line text-sm leading-relaxed text-ink">
              {session.abstract || "No description has been published yet."}
            </p>
            {session.topics.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {session.topics.map((t) => (
                  <span
                    key={t}
                    className="rounded-md bg-surface px-2 py-1 text-xs text-muted"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </Card>

          {session.speakers && session.speakers.length > 0 && (
            <Card>
              <h2 className="mb-2 font-semibold text-ink">Speakers</h2>
              <ul className="space-y-1.5 text-sm text-ink">
                {session.speakers.map((sp) => (
                  <li key={sp}>{sp}</li>
                ))}
              </ul>
            </Card>
          )}

          {planned && (
            <Card>
              <label htmlFor="session-note" className="mb-2 block font-semibold text-ink">
                Your notes
              </label>
              <textarea
                id="session-note"
                rows={4}
                value={planItem?.note?.text ?? ""}
                onChange={(e) => setNote(session.id, e.target.value)}
                placeholder="What did you learn? Any action items?"
                className={inputClass}
              />
              <p className="mt-2 text-xs text-muted">
                Saved in this browser. Rate the session and build your trip report on the{" "}
                <Link href="/notes" className="font-medium text-brand-purple hover:underline">
                  Notes
                </Link>{" "}
                page.
              </p>
            </Card>
          )}

          {related.length > 0 && (
            <section>
              <h2 className="mb-3 font-semibold text-ink">Related sessions</h2>
              <ul className="space-y-2">
                {related.map((s) => (
                  <SessionRow key={s.id} session={s} showDay />
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Side column */}
        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <Card>
            {!hydrated ? (
              <div className="h-[42px] animate-pulse rounded-lg bg-surface" aria-hidden />
            ) : planned ? (
              <Button
                variant="secondary"
                className="w-full py-2.5"
                onClick={() => removeFromPlan(session.id)}
              >
                <Check size={16} strokeWidth={2} aria-hidden />
                In your stack · Remove
              </Button>
            ) : (
              <Button className="w-full py-2.5" onClick={() => addToPlan(session.id)}>
                <Plus size={16} strokeWidth={2} aria-hidden />
                Add to stack
              </Button>
            )}

            <dl className="mt-3 divide-y divide-border">
              <Fact label="When">
                <span className="font-mono text-xs leading-relaxed">
                  {dayLong(session.start)}
                  <br />
                  {rangeLabel(session.start, session.end)} · {durationLabel(minutes)}
                </span>
              </Fact>
              <Fact label="Where">
                {session.venue}
                {session.room && <span className="block text-muted">{session.room}</span>}
              </Fact>
              <Fact label="Seating">
                {session.reservable ? "Reservable" : "Walk-up, no reservation"}
              </Fact>
              {session.roles.length > 0 && (
                <Fact label="Roles">{session.roles.join(", ")}</Fact>
              )}
              {session.industry && <Fact label="Industry">{session.industry}</Fact>}
            </dl>
          </Card>

          <Card>
            <h2 className="mb-1 font-semibold text-ink">Fit with your stack</h2>
            {fitFailed ? (
              <p className="text-sm text-muted">
                Your stack could not be checked. Reload the page to try again.
              </p>
            ) : !hydrated || !fit ? (
              <p className="text-sm text-muted">Checking your stack…</p>
            ) : session.reservable === false ? (
              <p className="text-sm text-muted">
                Walk-up items never block your schedule, so there is nothing to
                check.
              </p>
            ) : fit.conflicts.length === 0 && !fit.from && !fit.to ? (
              <p className="text-sm text-muted">
                Nothing else is planned around this time on{" "}
                {dayLong(session.start).split(",")[0]}. It fits.
              </p>
            ) : (
              <ul className="mt-2 space-y-3 text-sm">
                {fit.conflicts.map((c) => (
                  <li key={c.key} className="rounded-lg bg-error/10 p-3 text-error-fg">
                    Overlaps{" "}
                    <span className="font-semibold">
                      {otherLabel(c)} ({rangeLabel(c.start, c.end)})
                    </span>
                    . Pick one of the two.
                  </li>
                ))}
                {fit.from && fit.arrival && (
                  <li>
                    <div className="mb-1 text-muted">
                      Getting here from {otherLabel(fit.from)}, which ends{" "}
                      <span className="font-mono">{timeOf(fit.from.end)}</span> at{" "}
                      {fit.from.venue || "an unspecified venue"}
                    </div>
                    <FeasibilityBadge result={fit.arrival} />
                  </li>
                )}
                {fit.to && fit.departure && (
                  <li>
                    <div className="mb-1 text-muted">
                      Getting to {otherLabel(fit.to)} afterwards, which starts{" "}
                      <span className="font-mono">{timeOf(fit.to.start)}</span> at{" "}
                      {fit.to.venue || "an unspecified venue"}
                    </div>
                    <FeasibilityBadge result={fit.departure} />
                  </li>
                )}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
