"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CircleAlert,
  Search,
  SearchX,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { getSessions, getVenueGraph } from "@/lib/data";
import {
  applyFilters,
  buildFuse,
  countActiveFilters,
  dayOf,
  emptyFilters,
  parseNaturalLanguage,
} from "@/lib/search";
import { useCatalogView, type SortKey } from "@/lib/catalogView";
import { useCompassStore } from "@/lib/store";
import { dayLabel } from "@/lib/format";
import { rankSessions, topRoles } from "@/lib/ranking";
import { fitCheck, sessionToBlock, toBlocks } from "@/lib/schedule";
import { buildWalkLookup } from "@/lib/walkGraph";
import SessionCard from "@/components/SessionCard";
import FilterChips, { ActiveFilters } from "@/components/FilterChips";
import Button, { glassInputClass } from "@/components/ui/Button";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";
import Segmented from "@/components/ui/Segmented";
import Card from "@/components/ui/Card";

const PAGE_SIZE = 60;

const SORTS: { value: SortKey; label: string }[] = [
  { value: "relevance", label: "Best match for you" },
  { value: "time", label: "Start time" },
  { value: "title", label: "Title A to Z" },
];

const byTime = (a: Session, b: Session) =>
  a.start.localeCompare(b.start) || a.title.localeCompare(b.title);

export default function CatalogPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [graph, setGraph] = useState<VenueGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [showFilters, setShowFilters] = useState(false);

  const { filters, sort, nlQuery, nlExplanation, setFilters, setSort, setNl } =
    useCatalogView();
  const prefs = useCompassStore((s) => s.prefs);
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    Promise.all([getSessions(), getVenueGraph()])
      .then(([data, g]) => {
        setSessions(data);
        setGraph(g);
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fuse = useMemo(() => buildFuse(sessions), [sessions]);
  const tracks = useMemo(
    () => Array.from(new Set(sessions.map((s) => s.track))).sort(),
    [sessions]
  );
  const venues = useMemo(
    () => Array.from(new Set(sessions.map((s) => s.venue))).sort(),
    [sessions]
  );
  const roles = useMemo(() => topRoles(sessions, 10), [sessions]);
  const days = useMemo(
    () => Array.from(new Set(sessions.map(dayOf))).sort(),
    [sessions]
  );

  // Typing stays responsive: heavy filtering runs on a deferred copy.
  const deferredFilters = useDeferredValue(filters);
  const results = useMemo(() => {
    const list = applyFilters(sessions, deferredFilters, fuse);
    const searching = deferredFilters.text.trim().length > 0;
    switch (sort) {
      case "title":
        return [...list].sort((a, b) => a.title.localeCompare(b.title));
      case "time":
        return [...list].sort(byTime);
      default:
        // Best match: text relevance while searching, otherwise your profile.
        return searching ? list : rankSessions(list, prefs);
    }
  }, [sessions, deferredFilters, fuse, sort, prefs]);

  // Reset pagination whenever the result set changes.
  useEffect(() => {
    setVisible(PAGE_SIZE);
  }, [deferredFilters, sort]);

  const shown = results.slice(0, visible);

  // How each visible session fits around what is already in the stack.
  const lookup = useMemo(
    () => (graph ? buildWalkLookup(graph) : new Map<string, number>()),
    [graph]
  );
  const blocks = useMemo(
    () => toBlocks(plan, sessions, customItems),
    [plan, sessions, customItems]
  );
  const fits = useMemo(() => {
    if (blocks.length === 0) return null;
    return new Map(
      shown.map((s) => [s.id, fitCheck(sessionToBlock(s), blocks, lookup)])
    );
  }, [shown, blocks, lookup]);

  function runNaturalLanguage() {
    if (!nlQuery.trim()) {
      setNl("", null);
      return;
    }
    const { filters: parsed, explanation } = parseNaturalLanguage(nlQuery, sessions);
    setFilters({ ...emptyFilters, ...parsed });
    setNl(nlQuery, explanation);
  }

  const dayValue = filters.days.length === 1 ? filters.days[0] : filters.days.length === 0 ? "all" : "";
  const activeCount = countActiveFilters(filters);

  if (loadError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Catalog" />
        <EmptyState
          icon={CircleAlert}
          tone="error"
          title="The catalog did not load"
          body="Check your connection and try again."
          action={<Button onClick={load}>Try again</Button>}
        />
      </div>
    );
  }

  return (
    <div className="relative isolate space-y-6">
      <div className="glass-ambient" aria-hidden />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">
            re:Invent 2026
          </p>
          <PageHeader
            title="Find your next session"
            subtitle="Search, filter, and add the sessions that matter to your stack."
          />
        </div>
        <div className="rounded-xl border border-border bg-canvas/70 px-3 py-2 text-right shadow-card">
          <p className="font-mono text-lg font-semibold leading-none text-ink">
            {loading ? "—" : results.length.toLocaleString()}
          </p>
          <p className="mt-1 text-xs text-muted">sessions found</p>
        </div>
      </div>

      {/* Natural-language search (rules-based placeholder for the AWS AI). */}
      <Card glass className="overflow-hidden p-0">
        <div className="border-b border-[var(--glass-ring)] px-5 py-3.5">
          <label
            htmlFor="nl-query"
            className="flex items-center gap-2 text-sm font-semibold text-ink"
          >
            <Sparkles size={16} strokeWidth={1.75} className="text-brand-purple" aria-hidden />
            Describe what you want to learn
          </label>
          <p className="mt-1 text-xs text-muted">We’ll turn your request into useful catalog filters.</p>
        </div>
        <div className="flex flex-col gap-2 p-3 sm:flex-row sm:p-4">
          <input
            id="nl-query"
            value={nlQuery}
            onChange={(e) => setNl(e.target.value, nlExplanation)}
            onKeyDown={(e) => e.key === "Enter" && runNaturalLanguage()}
            placeholder="Advanced AI workshops on Wednesday near the Venetian"
            className={`${glassInputClass} flex-1`}
          />
          <Button variant="dark" onClick={runNaturalLanguage} disabled={loading} className="shrink-0">
            Interpret
          </Button>
        </div>
        {nlExplanation && (
          <p className="border-t border-[var(--glass-ring)] px-5 py-3 text-sm text-muted" aria-live="polite">
            {nlExplanation}
          </p>
        )}
      </Card>

      {/* Day tabs + sort */}
      <div className="rounded-2xl border border-border bg-canvas/70 p-3 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <CalendarDays size={16} className="shrink-0 text-brand-purple" aria-hidden />
            <Segmented
              glass
              ariaLabel="Filter by day"
              value={dayValue}
              onChange={(v) =>
                setFilters({ ...filters, days: v === "all" ? [] : [v] })
              }
              options={[
                { value: "all", label: "All days" },
                ...days.map((d) => ({ value: d, label: dayLabel(d) })),
              ]}
            />
          </div>
          <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            aria-expanded={showFilters}
            className="glass-pill inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg px-3 text-sm font-medium text-ink transition duration-200 lg:hidden"
          >
            <SlidersHorizontal size={16} strokeWidth={1.75} aria-hidden />
            Filters{activeCount > 0 ? ` (${activeCount})` : ""}
          </button>
          <label className="flex items-center gap-2 text-sm text-muted">
            Sort
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              className={`${glassInputClass} w-auto`}
            >
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          </div>
        </div>
      </div>

      <ActiveFilters filters={filters} onChange={setFilters} />

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside
          className={`${showFilters ? "block" : "hidden"} glass self-start rounded-2xl p-4 lg:sticky lg:top-6 lg:block`}
        >
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Refine results</h2>
            {activeCount > 0 && <span className="font-mono text-xs text-brand-purple">{activeCount} active</span>}
          </div>
          <div className="relative mb-2">
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <input
              value={filters.text}
              onChange={(e) => setFilters({ ...filters, text: e.target.value })}
              placeholder="Search the catalog"
              aria-label="Search sessions"
              className={`${glassInputClass} pl-9`}
            />
          </div>
          <FilterChips
            filters={filters}
            onChange={setFilters}
            tracks={tracks}
            venues={venues}
            roles={roles}
          />
        </aside>

        <div>
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2" aria-busy="true">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="glass h-52 animate-pulse rounded-2xl"
                />
              ))}
            </div>
          ) : results.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title="No sessions match"
              body="Remove a filter or try a broader search."
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setFilters(emptyFilters);
                    setNl("", null);
                  }}
                >
                  Clear all filters
                </Button>
              }
            />
          ) : (
            <>
              <div className="mb-3 flex items-center justify-between gap-3 px-1">
                <p className="text-sm font-medium text-ink">Browse sessions</p>
                <p className="font-mono text-xs text-muted">Showing {shown.length.toLocaleString()} of {results.length.toLocaleString()}</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {shown.map((s) => (
                  <SessionCard key={s.id} session={s} fit={fits?.get(s.id)} />
                ))}
              </div>
              {visible < results.length && (
                <div className="mt-6 text-center">
                  <Button
                    variant="secondary"
                    onClick={() => setVisible((v) => v + PAGE_SIZE)}
                  >
                    Show more ({(results.length - visible).toLocaleString()} remaining)
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
