// ---------------------------------------------------------------------------
// Core domain types for Builder Compass.
// These are intentionally transport-agnostic so the same shapes can be served
// from local mock JSON today or an AWS backend (API Gateway / AppSync) later.
// ---------------------------------------------------------------------------

// 0 == "No Level" (featured experiences, expo, etc.). 500 == Distinguished.
export type SessionLevel = 0 | 100 | 200 | 300 | 400 | 500;

// Values coming from the real re:Invent catalog. Kept as a string union of the
// known values; the loader maps raw CSV strings onto these.
export type SessionType =
  | "Breakout"
  | "Chalk Talk"
  | "Workshop"
  | "Builder Session"
  | "Code Talk"
  | "Lightning Talk"
  | "Keynote"
  | "Featured"
  | "Expo"
  | "Lab"
  | "Bootcamp"
  | "Exam prep"
  | "Gamified learning"
  | "Event service";

export interface Session {
  id: string; // e.g. "DEV301"
  code: string; // track prefix + number, usually same as id
  title: string;
  abstract: string;
  track: string; // "Developer Tools", "Serverless", ...
  level: SessionLevel;
  type: SessionType;
  roles: string[]; // targeted roles e.g. ["Developer", "DevOps Engineer"]
  topics: string[]; // tags used for ranking / NL search
  venue: string; // e.g. "Venetian"
  room: string; // e.g. "Level 2, Marcello 4501"
  start: string; // ISO datetime
  end: string; // ISO datetime
  reservable: boolean; // false => walk-up, no reservation needed
  speakers?: string[];
  industry?: string;
  lengthMinutes?: number;
}

// Walking graph between venues (approximate minutes on foot).
export interface WalkEdge {
  from: string; // venue name
  to: string; // venue name
  minutes: number;
}

export interface VenueGraph {
  venues: string[];
  edges: WalkEdge[];
}

export type PlanStatus = "planned" | "reserved" | "waitlist";

export interface SessionNote {
  text: string;
  updatedAt: string; // ISO datetime
}

export interface SessionRating {
  value: number; // 0 = not rated yet, otherwise 1..5
  wouldRecommend?: boolean; // undefined = not answered
  actionItems?: string;
  takeaway?: string;
}

export interface PlanItem {
  sessionId: string;
  status: PlanStatus;
  addedAt: string; // ISO datetime
  note?: SessionNote;
  rating?: SessionRating;
}

// A user-created block that is not a catalog session (party, meal, 1:1, etc.).
export interface CustomItem {
  id: string;
  title: string;
  venue?: string;
  room?: string;
  start: string; // ISO datetime
  end: string; // ISO datetime
  note?: string;
}

// Profile used to rank sessions, plan the week, and fill gaps.
export interface UserPrefs {
  interests: string[]; // lower-case topics, matched against Session.topics
  depth: SessionLevel; // preferred level (100..400)
  role: string; // one of the roles present in the catalog
  days: string[]; // YYYY-MM-DD the user attends; empty = all days
  includeEvents: boolean; // include parties / short featured events
  maxPerDay: number; // cap for auto-planned sessions per day
  goal: string; // free text: what do you want out of the week?
}

// Feasibility of reaching a session given the preceding block.
export type Feasibility = "comfortable" | "tight" | "not-happening" | "unknown";

export interface FeasibilityResult {
  feasibility: Feasibility;
  walkMinutes: number | null; // null when unknown
  gapMinutes: number | null; // minutes between previous end and this start
}
