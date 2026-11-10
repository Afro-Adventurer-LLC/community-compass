// ---------------------------------------------------------------------------
// Date/time formatting for session data.
//
// Catalog timestamps carry a Las Vegas (Pacific) offset, e.g.
// "2026-12-02T13:00:00-08:00". We format straight from the string so the
// wall-clock time shown is always the event's local time, whatever timezone
// the visitor's browser is in. (Going through `new Date().toLocaleTimeString`
// would silently shift times for anyone outside Pacific time.)
// ---------------------------------------------------------------------------

const VEGAS_OFFSET = "-08:00"; // PST — the whole event is in November/December

/** "13:00" from "2026-12-02T13:00:00-08:00". */
export function timeOf(iso: string): string {
  return iso.slice(11, 16);
}

/** "2026-12-02" from an ISO timestamp. */
export function dateOf(iso: string): string {
  return iso.slice(0, 10);
}

function utcNoon(date: string): Date {
  return new Date(`${date}T12:00:00Z`);
}

/** "Wed, Dec 2" from "2026-12-02" (or a full ISO timestamp). */
export function dayLabel(dateOrIso: string): string {
  return utcNoon(dateOrIso.slice(0, 10)).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** "Wednesday, Dec 2" */
export function dayLong(dateOrIso: string): string {
  return utcNoon(dateOrIso.slice(0, 10)).toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** "Wed" */
export function weekdayShort(dateOrIso: string): string {
  return utcNoon(dateOrIso.slice(0, 10)).toLocaleDateString("en-US", {
    weekday: "short",
    timeZone: "UTC",
  });
}

/** Lower-case full weekday name: "wednesday". */
export function weekdayName(dateOrIso: string): string {
  return utcNoon(dateOrIso.slice(0, 10))
    .toLocaleDateString("en-US", { weekday: "long", timeZone: "UTC" })
    .toLowerCase();
}

/** "13:00–14:00" */
export function rangeLabel(start: string, end: string): string {
  return `${timeOf(start)}–${timeOf(end)}`;
}

/** "1 h 30 min" / "45 min" */
export function durationLabel(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m} min`;
}

export function minutesBetween(fromIso: string, toIso: string): number {
  return Math.round(
    (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000
  );
}

/**
 * Convert a <input type="datetime-local"> value ("2026-12-02T18:00") into the
 * same offset-carrying format as catalog data. Custom blocks are entered in
 * Las Vegas time.
 */
export function toVegasIso(localValue: string): string {
  const withSeconds = localValue.length === 16 ? `${localValue}:00` : localValue;
  return `${withSeconds}${VEGAS_OFFSET}`;
}

/** "L300" or "No level". */
export function levelLabel(level: number): string {
  return level === 0 ? "No level" : `L${level}`;
}
