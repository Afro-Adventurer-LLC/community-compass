// ---------------------------------------------------------------------------
// Venue walk-graph helpers + feasibility calculation.
// Venues at re:Invent are kilometres apart, so a schedule must respect the
// walk between the previous block and the next one.
// ---------------------------------------------------------------------------

import type {
  Feasibility,
  FeasibilityResult,
  Session,
  VenueGraph,
} from "@/types";

const BUFFER_MINUTES = 10; // slack we want on top of the raw walk time

// Build a lookup of walk minutes between any two venues (symmetric).
export function buildWalkLookup(graph: VenueGraph): Map<string, number> {
  const lookup = new Map<string, number>();
  for (const edge of graph.edges) {
    lookup.set(`${edge.from}__${edge.to}`, edge.minutes);
    lookup.set(`${edge.to}__${edge.from}`, edge.minutes);
  }
  return lookup;
}

export function walkMinutes(
  lookup: Map<string, number>,
  from: string,
  to: string
): number | null {
  if (from === to) return 0; // same venue — assume a short in-building move
  const direct = lookup.get(`${from}__${to}`);
  return direct ?? null;
}

function minutesBetween(prevEndISO: string, nextStartISO: string): number {
  const prev = new Date(prevEndISO).getTime();
  const next = new Date(nextStartISO).getTime();
  return Math.round((next - prev) / 60000);
}

// Given the block immediately before `next`, how reachable is `next`?
export function feasibilityFor(
  previous: Pick<Session, "venue" | "end"> | null,
  next: Pick<Session, "venue" | "start">,
  lookup: Map<string, number>
): FeasibilityResult {
  if (!previous) {
    return { feasibility: "comfortable", walkMinutes: 0, gapMinutes: null };
  }

  const walk = walkMinutes(lookup, previous.venue, next.venue);
  const gap = minutesBetween(previous.end, next.start);

  if (walk === null) {
    return { feasibility: "unknown", walkMinutes: null, gapMinutes: gap };
  }

  let feasibility: Feasibility;
  if (walk === 0) {
    // Same venue: back-to-back sessions are fine (sessions end early enough
    // to change rooms); only an overlap is a problem, and conflicts cover it.
    feasibility = gap >= 0 ? "comfortable" : "not-happening";
  } else if (gap >= walk + BUFFER_MINUTES) {
    feasibility = "comfortable";
  } else if (gap >= walk) {
    feasibility = "tight";
  } else {
    feasibility = "not-happening";
  }

  return { feasibility, walkMinutes: walk, gapMinutes: gap };
}

// Do two blocks overlap in time?
export function overlaps(
  a: { start: string; end: string },
  b: { start: string; end: string }
): boolean {
  const aStart = new Date(a.start).getTime();
  const aEnd = new Date(a.end).getTime();
  const bStart = new Date(b.start).getTime();
  const bEnd = new Date(b.end).getTime();
  return aStart < bEnd && bStart < aEnd;
}
