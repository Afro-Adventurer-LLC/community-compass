// ---------------------------------------------------------------------------
// Convert the official-style re:Invent 2026 CSV export into the JSON shapes
// Builder Compass consumes (public/data/sessions.json + data/venues.json).
//
// Usage:
//   npm run convert-data -- path/to/reinvent2026_sessions.csv
//
// This is a build-time utility. When the real backend arrives, this logic can
// move server-side; the output shape stays identical.
// ---------------------------------------------------------------------------

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputArg = process.argv[2];
if (!inputArg) {
  console.error("Usage: npm run convert-data -- path/to/reinvent2026_sessions.csv");
  process.exit(1);
}
const inputPath = path.resolve(process.cwd(), inputArg);
const dataDir = path.resolve(__dirname, "../data");

// --- Minimal RFC-4180 CSV parser (handles quoted fields, commas, newlines) --
function parseCsv(text) {
  const rows = [];
  let field = "";
  let row = [];
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (c === "\r") {
      // ignore
    } else {
      field += c;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

// --- Mappers --------------------------------------------------------------

// Map the CSV "Type" strings onto the app's SessionType union (plus extras we
// keep verbatim so nothing is lost).
const TYPE_MAP = {
  "Breakout session": "Breakout",
  "Chalk talk": "Chalk Talk",
  Workshop: "Workshop",
  "Builders' session": "Builder Session",
  "Code talk": "Code Talk",
  "Lightning talk": "Lightning Talk",
  Keynote: "Keynote",
  Mainstage: "Keynote",
  "Featured experience": "Featured",
  Expo: "Expo",
  "Gamified learning": "Gamified learning",
  Lab: "Lab",
  "Event service": "Event service",
  Bootcamp: "Bootcamp",
  "Exam prep": "Exam prep",
};

function mapType(raw) {
  return TYPE_MAP[raw?.trim()] ?? raw?.trim() ?? "Breakout";
}

// Parse the leading number out of "300 – Advanced" etc. "No Level" -> 0.
function mapLevel(raw) {
  if (!raw) return 0;
  const m = raw.match(/(\d{3})/);
  return m ? Number(m[1]) : 0;
}

// Normalize a "Venue/Room" string into { venue, room }.
// Examples:
//   "Venetian | Level 2 | Hall A"        -> Venetian / Level 2, Hall A
//   "TAP Sports Bar (located in MGM Grand)" -> MGM Grand / TAP Sports Bar
//   "Wynn/Encore | Ballroom"             -> Wynn/Encore / Ballroom
function normalizeVenueRoom(raw) {
  const value = (raw || "").trim();
  if (!value) return { venue: "TBD", room: "" };

  const parts = value.split("|").map((p) => p.trim());
  let head = parts[0];
  const rest = parts.slice(1).join(", ");

  // Pull out "(located in X)" -> parent venue becomes X, satellite is the room.
  const located = head.match(/^(.*?)\s*\(located in (.*?)\)\s*$/i);
  if (located) {
    const satellite = located[1].trim();
    const parent = located[2].trim().replace(/^The\s+/i, "");
    return {
      venue: parent,
      room: [satellite, rest].filter(Boolean).join(", "),
    };
  }

  return { venue: head, room: rest };
}

function splitList(raw) {
  if (!raw) return [];
  return raw
    .split(/[;,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// Speakers are separated by ";" only — each name contains commas inside its
// "(Title, Company)" suffix, so we must NOT split on commas here.
function splitSpeakers(raw) {
  if (!raw) return [];
  return raw
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
}

function toIso(dateStr, timeStr) {
  // dateStr: YYYY-MM-DD, timeStr: HH:MM. re:Invent is Pacific (-08:00 in Dec).
  if (!dateStr || !timeStr) return null;
  return `${dateStr}T${timeStr.length === 5 ? timeStr : timeStr}:00-08:00`;
}

// --- Walk graph -----------------------------------------------------------
// Approximate walking minutes between the main re:Invent 2026 campuses.
// Satellite locations are normalized to their parent above, so these parents
// cover the schedule. Unknown pairs fall back to "unknown" in the UI.
const WALK_EDGES = [
  ["Venetian", "Caesars Forum", 18],
  ["Venetian", "Caesars Palace", 15],
  ["Venetian", "Wynn/Encore", 12],
  ["Venetian", "MGM Grand", 28],
  ["Venetian", "Allegiant Stadium", 45],
  ["Caesars Forum", "Caesars Palace", 8],
  ["Caesars Forum", "Wynn/Encore", 22],
  ["Caesars Forum", "MGM Grand", 20],
  ["Caesars Forum", "Allegiant Stadium", 40],
  ["Caesars Palace", "Wynn/Encore", 20],
  ["Caesars Palace", "MGM Grand", 22],
  ["Caesars Palace", "Allegiant Stadium", 42],
  ["Wynn/Encore", "MGM Grand", 32],
  ["Wynn/Encore", "Allegiant Stadium", 48],
  ["MGM Grand", "Allegiant Stadium", 18],
];

// --- Run ------------------------------------------------------------------

const raw = fs.readFileSync(inputPath, "utf8");
const rows = parseCsv(raw);
const header = rows[0];
const idx = Object.fromEntries(header.map((h, i) => [h.trim(), i]));
const dataRows = rows
  .slice(1)
  .filter((r) => r.length >= header.length && (r[idx["Code"]] || "").trim());

const sessions = [];
const venueSet = new Set();

for (const r of dataRows) {
  const get = (k) => (r[idx[k]] ?? "").trim();
  const code = get("Code");
  const { venue, room } = normalizeVenueRoom(get("Venue/Room"));
  venueSet.add(venue);

  const start = toIso(get("Date"), get("Start"));
  const end = toIso(get("Date"), get("End"));

  // Topics: combine Topic + Area of Interest + Services for search/ranking.
  const topics = Array.from(
    new Set([
      ...splitList(get("Topic")),
      ...splitList(get("Area of Interest")),
      ...splitList(get("Services")),
    ])
  )
    .map((t) => t.toLowerCase())
    .slice(0, 12);

  // Primary track = first Topic segment (Topic is multi-valued, ";"-joined).
  const primaryTrack =
    splitList(get("Topic"))[0] ||
    splitList(get("Area of Interest"))[0] ||
    "General";

  sessions.push({
    id: code,
    code,
    title: get("Title"),
    abstract: get("Description"),
    track: primaryTrack,
    level: mapLevel(get("Level")),
    type: mapType(get("Type")),
    roles: splitList(get("Role")),
    topics,
    venue,
    room,
    start: start ?? "",
    end: end ?? "",
    reservable: !/Featured experience|Expo|Event service|Gamified/i.test(
      get("Type")
    ),
    speakers: splitSpeakers(get("Speakers")),
    industry: get("Industry") || undefined,
    lengthMinutes: Number(get("Length (min)")) || undefined,
  });
}

// Build venue graph: only include edges where both venues appear in the data.
const venues = Array.from(venueSet).sort();
const edges = WALK_EDGES.filter(
  ([a, b]) => venueSet.has(a) && venueSet.has(b)
).map(([from, to, minutes]) => ({ from, to, minutes }));

fs.mkdirSync(dataDir, { recursive: true });
// The catalog is served as a static file (fetched by the client, imported by
// server components), so it lives in public/ and is written minified.
const publicDataDir = path.join(dataDir, "..", "public", "data");
fs.mkdirSync(publicDataDir, { recursive: true });
fs.writeFileSync(
  path.join(publicDataDir, "sessions.json"),
  JSON.stringify(sessions)
);
fs.writeFileSync(
  path.join(dataDir, "venues.json"),
  JSON.stringify({ venues, edges }, null, 2)
);

console.log(`Wrote ${sessions.length} sessions.`);
console.log(`Venues (${venues.length}): ${venues.join(", ")}`);
console.log(`Walk edges: ${edges.length}`);
const missing = venues.filter(
  (v) => !edges.some((e) => e.from === v || e.to === v)
);
if (missing.length) {
  console.log(`Venues with no walk edges (UI shows "unknown"): ${missing.join(", ")}`);
}
