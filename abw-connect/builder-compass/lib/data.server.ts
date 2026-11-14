// ---------------------------------------------------------------------------
// Server-only catalog access for server components (home page, session pages).
// The import below is resolved at build time into the server bundle only;
// `server-only` makes the build fail if a client component ever imports this.
// ---------------------------------------------------------------------------

import "server-only";
import sessionsJson from "@/public/data/sessions.json";
import type { Session } from "@/types";

const sessions = sessionsJson as Session[];
const byId = new Map(sessions.map((s) => [s.id, s]));

export function loadSessions(): Session[] {
  return sessions;
}

export function findSession(id: string): Session | undefined {
  return byId.get(id);
}

/** Reservable sessions in the same track sharing at least two topics. */
export function relatedSessions(session: Session, limit = 4): Session[] {
  const mine = new Set(session.topics);
  return sessions
    .filter((s) => s.id !== session.id && s.reservable && s.track === session.track)
    .map((s) => ({ s, shared: s.topics.filter((t) => mine.has(t)).length }))
    .filter(({ shared }) => shared >= 2)
    .sort(
      (a, b) =>
        b.shared - a.shared ||
        Math.abs(a.s.level - session.level) - Math.abs(b.s.level - session.level) ||
        a.s.start.localeCompare(b.s.start)
    )
    .slice(0, limit)
    .map(({ s }) => s);
}
