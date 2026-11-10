// ---------------------------------------------------------------------------
// Data access layer (client side) — the single swap point for a real backend.
//
// The catalog is a static file (public/data/sessions.json) fetched once and
// cached, so it is never part of the JavaScript bundle. Later, your team can
// point SESSIONS_URL at an AWS backend (API Gateway + Lambda, or AppSync)
// WITHOUT touching any UI code, because the rest of the app only imports from
// here. Server components read the same file through lib/data.server.ts.
// ---------------------------------------------------------------------------

import venuesJson from "@/data/venues.json";
import type { Session, VenueGraph } from "@/types";

export const SESSIONS_URL = "/data/sessions.json";

let sessionsPromise: Promise<Session[]> | null = null;

/** The full catalog, fetched once per page load and shared by every caller. */
export function getSessions(): Promise<Session[]> {
  if (!sessionsPromise) {
    sessionsPromise = fetch(SESSIONS_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Catalog request failed: ${res.status}`);
        return res.json() as Promise<Session[]>;
      })
      .catch((err) => {
        sessionsPromise = null; // let the next caller retry
        throw err;
      });
  }
  return sessionsPromise;
}

// The venue graph is tiny (~1.5 KB), so it stays bundled.
export async function getVenueGraph(): Promise<VenueGraph> {
  return venuesJson as VenueGraph;
}

export function venueGraphSync(): VenueGraph {
  return venuesJson as VenueGraph;
}
