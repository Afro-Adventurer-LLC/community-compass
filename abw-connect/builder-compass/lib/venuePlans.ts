// ---------------------------------------------------------------------------
// Simplified isometric floor plans for each re:Invent venue.
// Coordinates are plan units on a per-level plate: x runs along the long axis,
// y runs toward the viewer. Layouts are condensed from the venues' published
// meeting-space maps (not survey-accurate) and rooms are linked to the session
// catalog through `match` (first matching room wins).
// ---------------------------------------------------------------------------

export type Tone =
  | "violet" | "blue" | "cyan" | "green" | "lime"
  | "yellow" | "orange" | "red" | "pink" | "neutral";

export type PlanRoom = {
  id: string;
  name: string;
  x: number;
  y: number;
  w: number;
  d: number;
  tone: Tone;
  /** Lower-cased fragments matched against a session's room string. */
  match?: string[];
  /** Extrusion height override (plan units). */
  h?: number;
};

export type PlanLevel = {
  id: string;
  tab: string;
  label: string;
  size: [number, number];
  /** Offset of the plate along x so smaller upper floors can sit to one side. */
  ox?: number;
  rooms: PlanRoom[];
};

export type VenuePlan = { note: string; levels: PlanLevel[] };

const r = (
  id: string, name: string, x: number, y: number, w: number, d: number,
  tone: Tone, match: string[] = [], h?: number
): PlanRoom => ({ id, name, x, y, w, d, tone, match, h });

export const VENUE_PLANS: Record<string, VenuePlan> = {
  Venetian: {
    note: "Sands Expo and Venetian ballroom levels",
    levels: [
      { id: "l1", tab: "Level 1", label: "Level 1 · Hall G and meeting rooms", size: [100, 60], rooms: [
        r("hall-g", "Hall G", 0, 12, 60, 40, "lime", ["hall g", "expo lower foyer"]),
        r("rooms", "Rooms 101–407", 60, 22, 22, 30, "cyan", ["room 101", "room 407"]),
        r("casanova", "Casanova", 82, 22, 18, 10, "violet", ["casanova"]),
        r("marco", "Marco Polo", 82, 32, 18, 10, "pink", ["marco polo"]),
        r("galileo", "Galileo", 82, 42, 18, 10, "red", ["galileo"]),
        r("entrance", "Main entrance", 18, 52, 24, 8, "neutral", [], 0.8),
      ] },
      { id: "l2", tab: "Level 2", label: "Level 2 · Expo halls and ballrooms", size: [100, 60], rooms: [
        r("hall-a", "Hall A", 0, 0, 22, 36, "violet", ["hall a"]),
        r("hall-b", "Hall B", 22, 0, 22, 36, "orange", ["hall b"]),
        r("hall-c", "Hall C", 44, 0, 22, 36, "pink", ["hall c"]),
        r("hall-d", "Hall D", 66, 0, 16, 36, "green", ["hall d"]),
        r("ball-e", "Ballroom E", 82, 0, 18, 16, "blue", ["ballroom e"]),
        r("ball-f", "Ballroom F", 82, 16, 18, 20, "cyan", ["ballroom f"]),
        r("veronese", "Veronese", 0, 40, 16, 20, "violet", ["veronese"]),
        r("bassano", "Bassano", 16, 40, 16, 20, "blue", ["bassano"]),
        r("titian", "Titian", 32, 40, 16, 20, "green", ["titian"]),
        r("bellini", "Bellini", 48, 40, 16, 20, "yellow", ["bellini"]),
        r("theatre", "Venetian Theatre", 66, 40, 34, 20, "pink", ["venetian theatre"]),
      ] },
      { id: "l3", tab: "Level 3", label: "Level 3 · Meeting rooms", size: [72, 22], ox: 28, rooms: [
        r("toscana", "Toscana", 0, 0, 18, 22, "green", ["toscana"]),
        r("sanpolo", "San Polo", 18, 0, 18, 22, "yellow", ["san polo"]),
        r("murano", "Murano", 36, 0, 18, 22, "orange", ["murano"]),
        r("lido", "Lido", 54, 0, 18, 22, "cyan", ["lido"]),
      ] },
      { id: "l4", tab: "Level 4", label: "Level 4 · Meeting rooms", size: [72, 22], ox: 28, rooms: [
        r("zeno", "Zeno", 0, 0, 18, 22, "red", ["zeno"]),
        r("marcello", "Marcello", 18, 0, 18, 22, "pink", ["marcello"]),
        r("lando", "Lando", 36, 0, 18, 22, "orange", ["lando"]),
        r("delfino", "Delfino", 54, 0, 18, 22, "yellow", ["delfino"]),
      ] },
      { id: "l5", tab: "Level 5", label: "Level 5 · Palazzo Ballroom", size: [56, 24], ox: 44, rooms: [
        r("palazzo", "Palazzo Ballroom", 0, 0, 56, 24, "blue", ["palazzo"]),
      ] },
    ],
  },

  "Wynn/Encore": {
    note: "Convention promenades and Encore ballrooms",
    levels: [
      { id: "lower", tab: "Lower", label: "Lower Convention Promenade", size: [100, 40], rooms: [
        r("meursault", "Meursault", 0, 0, 34, 40, "blue", ["meursault"]),
        r("castillon", "Castillon", 34, 0, 33, 40, "orange", ["castillon"]),
        r("fleurie", "Fleurie", 67, 0, 33, 40, "pink", ["fleurie"]),
      ] },
      { id: "promenade", tab: "Promenade", label: "Convention Promenade", size: [100, 44], rooms: [
        r("montrachet", "Montrachet", 0, 0, 20, 44, "violet", ["montrachet"]),
        r("latache", "La Tâche", 20, 0, 20, 44, "red", ["la tache"]),
        r("margaux", "Margaux", 40, 0, 20, 44, "green", ["margaux"]),
        r("latour", "Latour", 60, 0, 24, 44, "cyan", ["latour"]),
        r("mouton", "Mouton", 84, 0, 16, 44, "yellow", ["mouton"]),
      ] },
      { id: "upper", tab: "Upper", label: "Upper Convention Promenade", size: [100, 44], rooms: [
        r("cristal", "Cristal 1–7", 0, 0, 76, 44, "violet", ["cristal"]),
        r("bollinger", "Bollinger", 76, 0, 24, 44, "green", ["bollinger"]),
      ] },
      { id: "encore", tab: "Encore", label: "Encore · Level 1", size: [100, 44], rooms: [
        r("encore-ball", "Encore Ballroom", 0, 0, 50, 44, "orange", ["encore ballroom"]),
        r("chopin", "Chopin", 50, 0, 20, 44, "pink", ["chopin"]),
        r("debussy", "Debussy", 70, 0, 15, 44, "blue", ["debussy"]),
        r("brahms", "Brahms", 85, 0, 15, 44, "cyan", ["brahms"]),
      ] },
    ],
  },

  "MGM Grand": {
    note: "Conference Center levels 1 and 3",
    levels: [
      { id: "l1", tab: "Level 1", label: "Level 1 · Grand and Boulevard rooms", size: [100, 56], rooms: [
        r("grand", "Grand 111–124", 0, 0, 50, 30, "orange", ["grand 1"]),
        r("boulevard", "Boulevard 155–167", 50, 0, 30, 30, "pink", ["boulevard"]),
        r("terrace", "Terrace 153", 80, 0, 20, 30, "green", ["terrace"]),
        r("room104", "Room 104", 0, 34, 20, 22, "cyan", ["room 104"]),
        r("lobby", "Conference lobby", 20, 34, 40, 22, "neutral", [], 0.8),
      ] },
      { id: "l3", tab: "Level 3", label: "Level 3 · Premier and Content Hub", size: [100, 56], rooms: [
        r("premier", "Premier 309–320", 0, 0, 60, 28, "violet", ["premier"]),
        r("chairmans", "Chairman’s 363", 60, 0, 40, 28, "blue", ["chairman"]),
        r("rooms3", "Rooms 301–353", 0, 32, 60, 24, "cyan", ["room 3"]),
        r("prefunction", "Pre-Function", 60, 32, 40, 24, "neutral", ["pre-function"], 0.8),
      ] },
    ],
  },

  "Caesars Palace": {
    note: "Conference Center ballroom levels",
    levels: [
      { id: "promenade", tab: "Promenade", label: "Promenade Level", size: [100, 56], rooms: [
        r("octavius", "Octavius", 0, 0, 56, 28, "blue", ["octavius"]),
        r("trevi", "Trevi", 56, 0, 22, 28, "pink", ["trevi"]),
        r("neo", "Neopolitan", 78, 0, 22, 28, "orange", ["neopolitan"]),
        r("roman", "Roman", 0, 32, 28, 24, "red", ["roman"]),
        r("milano", "Milano", 28, 32, 36, 24, "green", ["milano"]),
        r("pompeian", "Pompeian", 64, 32, 36, 24, "violet", ["pompeian"]),
      ] },
      { id: "emperors", tab: "Emperors", label: "Emperors Level", size: [100, 56], rooms: [
        r("palace", "Palace Ballroom", 0, 0, 44, 56, "violet", ["palace ballroom"]),
        r("augustus", "Augustus Ballroom", 44, 0, 30, 56, "orange", ["augustus"]),
        r("emperors", "Emperors Ballroom", 74, 0, 26, 56, "blue", ["emperors ballroom"]),
      ] },
    ],
  },

  "Caesars Forum": {
    note: "Forum ballroom, Alliance and Academy rooms",
    levels: [
      { id: "l1", tab: "Level 1", label: "Level 1 · Forum", size: [100, 60], rooms: [
        r("forum120", "Forum 120 · Content Hub", 0, 0, 48, 32, "violet", ["forum 120"]),
        r("forum1xx", "Forum 101–114", 0, 32, 48, 18, "blue", ["forum 10", "forum 11"]),
        r("prefn", "Pre-Function", 0, 50, 48, 10, "neutral", ["pre-function"], 0.8),
        r("alliance", "Alliance 305–314", 48, 0, 26, 60, "orange", ["alliance"]),
        r("academy", "Academy 409–417", 74, 0, 26, 60, "green", ["academy"]),
      ] },
    ],
  },

  "Allegiant Stadium": {
    note: "050 Level concourse orientation",
    levels: [
      { id: "l050", tab: "050 Level", label: "050 Level concourse", size: [100, 70], rooms: [
        r("east", "East VIP club", 28, 4, 44, 12, "blue", ["east"]),
        r("field", "Field", 24, 20, 52, 30, "green", ["field"], 0.8),
        r("west", "West VIP club", 28, 54, 44, 12, "violet", ["west"]),
      ] },
    ],
  },
};
