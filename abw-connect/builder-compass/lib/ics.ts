// ---------------------------------------------------------------------------
// Calendar export (iCalendar / .ics). Times are written in UTC, so they land
// at the right moment in Apple Calendar, Google Calendar, and Outlook
// regardless of the viewer's timezone.
// ---------------------------------------------------------------------------

import type { Block } from "@/lib/schedule";

function utcStamp(iso: string): string {
  return new Date(iso)
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d{3}/, "");
}

function escapeText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n");
}

// RFC 5545: lines should be at most 75 octets; continuation lines start with a space.
function fold(line: string): string[] {
  const parts: string[] = [];
  let rest = line;
  let first = true;
  while (rest.length > (first ? 70 : 69)) {
    const size = first ? 70 : 69;
    parts.push((first ? "" : " ") + rest.slice(0, size));
    rest = rest.slice(size);
    first = false;
  }
  parts.push((first ? "" : " ") + rest);
  return parts;
}

function describe(b: Block): string {
  if (b.kind === "custom") return "Custom block added in Builder Compass.";
  const s = b.session;
  if (!s) return "";
  return [
    s.type,
    s.track,
    s.level ? `Level ${s.level}` : null,
    s.reservable ? null : "Walk-up, no reservation",
    b.status ? `Status: ${b.status}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function blocksToIcs(blocks: Block[], now: Date = new Date()): string {
  const stamp = utcStamp(now.toISOString());
  const lines: string[] = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Builder Compass//re:Invent 2026//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "X-WR-CALNAME:re:Invent 2026 (Builder Compass)",
  ];

  for (const b of blocks) {
    const summary = b.code ? `${b.code}: ${b.title}` : b.title;
    const location = [b.venue, b.room].filter(Boolean).join(", ");
    lines.push(
      "BEGIN:VEVENT",
      `UID:${b.key.replace(/[^A-Za-z0-9-]/g, "-")}@builder-compass`,
      `DTSTAMP:${stamp}`,
      `DTSTART:${utcStamp(b.start)}`,
      `DTEND:${utcStamp(b.end)}`,
      `SUMMARY:${escapeText(summary)}`
    );
    if (location) lines.push(`LOCATION:${escapeText(location)}`);
    const description = describe(b);
    if (description) lines.push(`DESCRIPTION:${escapeText(description)}`);
    lines.push("END:VEVENT");
  }

  lines.push("END:VCALENDAR");
  return lines.flatMap(fold).join("\r\n") + "\r\n";
}
