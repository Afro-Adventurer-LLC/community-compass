"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Building2,
  Car,
  CircleAlert,
  Clock3,
  Footprints,
  Hotel,
  MapPin,
  Navigation,
  Route,
  Sparkles,
  Trophy,
} from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { getSessions, getVenueGraph } from "@/lib/data";
import { useCompassStore, useHydrated } from "@/lib/store";
import { dateOf, dayLabel, rangeLabel } from "@/lib/format";
import { toBlocks } from "@/lib/schedule";
import { buildWalkLookup, walkMinutes } from "@/lib/walkGraph";
import Card from "@/components/ui/Card";
import VenueIsoPlan from "@/components/VenueIsoPlan";
import { VENUE_PLANS } from "@/lib/venuePlans";
import EmptyState from "@/components/ui/EmptyState";
import PageHeader from "@/components/ui/PageHeader";
import Segmented from "@/components/ui/Segmented";

// Map space is a 960 × 600 canvas, north up. The Strip leans ~11° like the real
// street grid, so every footprint is rotated by STRIP_TILT.
const MAP_W = 960;
const MAP_H = 600;
const STRIP_TILT = 11.3;

const SKYLINE_BUILDINGS = [
  { left: "3%", width: "7%", height: "34%" }, { left: "11%", width: "5%", height: "52%" },
  { left: "17%", width: "10%", height: "42%" }, { left: "29%", width: "6%", height: "68%" },
  { left: "36%", width: "11%", height: "50%" }, { left: "49%", width: "7%", height: "78%" },
  { left: "57%", width: "12%", height: "40%" }, { left: "70%", width: "6%", height: "58%" },
  { left: "78%", width: "10%", height: "46%" }, { left: "90%", width: "6%", height: "64%" },
];

type StopType = "venue" | "hotel" | "stadium";
type Side = "left" | "right" | "below";
type Stop = { name: string; label: string; x: number; y: number; w: number; h: number; type: StopType; side: Side };

// Positions follow the real street plan: Las Vegas Blvd runs NNE–SSW; Wynn,
// Venetian, Caesars Forum (behind the LINQ, on Koval) and MGM Grand are on the
// east side; Treasure Island and Caesars Palace on the west; Allegiant Stadium
// is west of I-15. Cross streets keep their order north to south: Spring
// Mountain / Sands, Flamingo, Tropicana. Not to scale.
const TOP_DOWN_STOPS: Stop[] = [
  { name: "Wynn/Encore", label: "Wynn / Encore", x: 655, y: 70, w: 110, h: 96, type: "venue", side: "right" },
  { name: "Treasure Island", label: "Treasure Island", x: 468, y: 195, w: 92, h: 62, type: "hotel", side: "left" },
  { name: "Venetian", label: "Venetian", x: 618, y: 224, w: 100, h: 80, type: "venue", side: "right" },
  { name: "Caesars Palace", label: "Caesars Palace", x: 448, y: 278, w: 116, h: 84, type: "venue", side: "left" },
  { name: "Caesars Forum", label: "Caesars Forum", x: 604, y: 312, w: 88, h: 72, type: "venue", side: "right" },
  { name: "MGM Grand", label: "MGM Grand", x: 566, y: 455, w: 112, h: 90, type: "venue", side: "right" },
  { name: "Allegiant Stadium", label: "Allegiant Stadium", x: 128, y: 522, w: 116, h: 92, type: "stadium", side: "below" },
];

// Cartographic geometry (Strip, I-15, Koval, cross streets) for the base map.
// Roads run parallel to the Strip (dx/dy = -0.2, i.e. STRIP_TILT); cross
// streets are perpendicular to it.
const STRIP_PATH = "M 590 -20 L 462 620";
const KOVAL_PATH = "M 681 175 L 592 620"; // starts at Sands Ave
const I15_PATH = "M 330 -20 L 202 620";
const CROSS_STREETS = [
  { name: "Spring Mountain Rd", d: "M -20 35 L 980 235", label: 0.1 },
  { name: "Flamingo Rd", d: "M -20 232 L 980 432", label: 0.1 },
  { name: "Tropicana Ave", d: "M -20 420 L 980 620", label: 0.1 },
];
const PARKS = [
  // Wynn Golf Club, east of Wynn
  "M 790 30 Q 860 6 925 40 Q 950 92 915 140 Q 850 162 800 128 Q 770 80 790 30 Z",
  "M 120 60 Q 190 40 250 70 Q 262 120 220 150 Q 150 160 118 120 Q 100 90 120 60 Z",
  "M 760 470 Q 812 446 868 474 Q 884 520 846 548 Q 790 556 764 520 Z",
];

const REFERENCE_PLANS: Record<string, { image: string; title: string; source: string }> = {
  Venetian: {
    image: "/maps/references/venetian-level-1.jpg",
    title: "Venetian Expo reference floor plan",
    source: "https://www.venetianlasvegas.com/meetings/resources.html",
  },
  "Wynn/Encore": {
    image: "/maps/references/wynn-meeting-map.jpg",
    title: "Wynn ballrooms and meeting rooms reference map",
    source: "https://www.wynnlasvegas.com/meetings",
  },
  "MGM Grand": {
    image: "/maps/references/mgm-conference-map.jpg",
    title: "MGM Grand conference-center reference map",
    source: "https://mgmgrand.mgmresorts.com/en/meetings-groups/document-library.html",
  },
  "Caesars Palace": {
    image: "/maps/references/caesars-palace-conference-map.jpg",
    title: "Caesars Palace Conference Center floor plan",
    source: "https://www.caesars.com/content/dam/meetings/PDFs/FloorPlans/Caesars_Palace_Las_Vegas-2014-FLOOR-PLAN.pdf",
  },
  "Caesars Forum": {
    image: "/maps/references/caesars-forum-venue-map.jpg",
    title: "Caesars Forum venue floor plan",
    source: "https://www.indeedevents.com/wp-content/uploads/2024/04/UNAM24_FLOORPLAN_WEB-02.pdf",
  },
  "Allegiant Stadium": {
    image: "/maps/references/allegiant-050-level-map.jpg",
    title: "Allegiant Stadium 050 level map",
    source: "https://www.allegiantstadium.com/stadium-maps",
  },
};

function pointFor(venue: string) {
  return TOP_DOWN_STOPS.find((stop) => stop.name === venue && stop.type !== "hotel");
}

function topDownStop(name: string) {
  return TOP_DOWN_STOPS.find((stop) => stop.name === name);
}

const pct = (value: number, total: number) => `${((value / total) * 100).toFixed(2)}%`;

// A gentle arc between two stops, like a routing overlay in a maps app.
function arcBetween(a: Stop, b: Stop) {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const bend = Math.min(60, Math.hypot(dx, dy) * 0.18);
  const len = Math.hypot(dx, dy) || 1;
  return `M ${a.x} ${a.y} Q ${mx - (dy / len) * bend} ${my + (dx / len) * bend} ${b.x} ${b.y}`;
}

function StopIcon({ type }: { type: StopType }) {
  const Icon = type === "hotel" ? Hotel : type === "stadium" ? Trophy : Building2;
  return <Icon size={14} strokeWidth={2.25} aria-hidden />;
}

function estimatedTravelMinutes(lookup: Map<string, number>, from: string, to: string) {
  if (from === to) return 0;
  const known = walkMinutes(lookup, from, to);
  if (known !== null && known > 0) return known;
  const origin = topDownStop(from);
  const destination = topDownStop(to);
  if (!origin || !destination) return 15;
  const dy = (Math.abs(origin.y - destination.y) / MAP_H) * 100;
  const dx = (Math.abs(origin.x - destination.x) / MAP_W) * 100;
  return Math.max(4, Math.round(dy * 0.43 + dx * 0.18));
}

export default function MapPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [graph, setGraph] = useState<VenueGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [selectedVenue, setSelectedVenue] = useState("Venetian");
  const [selectedDay, setSelectedDay] = useState("");
  const [travelFrom, setTravelFrom] = useState("Venetian");
  const [travelTo, setTravelTo] = useState("Caesars Forum");

  const hydrated = useHydrated();
  const plan = useCompassStore((s) => s.plan);
  const customItems = useCompassStore((s) => s.customItems);

  useEffect(() => {
    Promise.all([getSessions(), getVenueGraph()])
      .then(([data, g]) => {
        setSessions(data);
        setGraph(g);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, []);

  const lookup = useMemo(
    () => (graph ? buildWalkLookup(graph) : new Map<string, number>()),
    [graph]
  );
  const blocks = useMemo(
    () => toBlocks(plan, sessions, customItems).filter((block) => pointFor(block.venue)),
    [plan, sessions, customItems]
  );
  const venueCounts = useMemo(() => {
    const counts = new Map<string, number>();
    sessions.forEach((session) => counts.set(session.venue, (counts.get(session.venue) ?? 0) + 1));
    return counts;
  }, [sessions]);
  const selectedSessions = useMemo(
    () => sessions.filter((session) => session.venue === selectedVenue).sort((a, b) => a.start.localeCompare(b.start)),
    [sessions, selectedVenue]
  );
  const selectedRooms = useMemo(() => {
    const rooms = new Map<string, number>();
    selectedSessions.forEach((session) => {
      const name = session.room || "Session spaces";
      rooms.set(name, (rooms.get(name) ?? 0) + 1);
    });
    return Array.from(rooms.entries()).sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [selectedSessions]);
  const referencePlan = REFERENCE_PLANS[selectedVenue];
  const travelWalk = estimatedTravelMinutes(lookup, travelFrom, travelTo);
  const rideshareLow = Math.max(4, Math.round(travelWalk * 0.32 + 2));
  const rideshareHigh = rideshareLow + 4;
  const routeDays = useMemo(
    () => Array.from(new Set(blocks.map((block) => dateOf(block.start)))).sort(),
    [blocks]
  );
  const activeDay = selectedDay || routeDays[0] || "";
  const routeBlocks = useMemo(
    () => blocks.filter((block) => dateOf(block.start) === activeDay).sort((a, b) => a.start.localeCompare(b.start)),
    [blocks, activeDay]
  );
  const routeLegs = useMemo(
    () => routeBlocks.slice(1).map((block, index) => {
      const previous = routeBlocks[index];
      return {
        from: previous,
        to: block,
        minutes: previous.venue && block.venue ? walkMinutes(lookup, previous.venue, block.venue) : null,
      };
    }),
    [routeBlocks, lookup]
  );

  if (failed) {
    return <div className="space-y-6"><PageHeader title="Venues" /><EmptyState icon={CircleAlert} tone="error" title="Venue data did not load" body="Reload the page to try again." /></div>;
  }

  if (loading || !graph || !hydrated) {
    return <div className="space-y-6" aria-busy="true"><PageHeader title="Venues" subtitle="Loading the Strip map…" /><div className="h-[540px] animate-pulse rounded-2xl border border-border bg-canvas" /></div>;
  }

  return (
    <div className="relative isolate space-y-6">
      <div className="glass-ambient" aria-hidden />
      <div>
        <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">Navigate re:Invent</p>
        <PageHeader title="The Strip, mapped for your week" subtitle="Explore the venues, compare typical walking times, and trace the route from your Stack." />
      </div>

      <section className="vegas-skyline overflow-hidden rounded-2xl border border-[var(--glass-border)]" aria-label="Stylized Las Vegas skyline">
        <div className="vegas-skyline-glow" aria-hidden />
        <div className="vegas-skyline-buildings" aria-hidden>
          {SKYLINE_BUILDINGS.map((building, index) => <span key={index} style={building} />)}
        </div>
        <div className="vegas-skyline-content">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/50 bg-white/45 px-3 py-1 font-mono text-xs font-semibold text-brand-purple backdrop-blur"><Sparkles size={13} />ON THE STRIP</span>
          <p className="mt-3 max-w-md text-lg font-semibold text-ink">Your venue guide follows the flow of Vegas, not a maze of lines.</p>
        </div>
        <span className="vegas-skyline-light" aria-hidden />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px] xl:items-start">
        <Card glass className="overflow-hidden p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--glass-ring)] px-5 py-4">
            <div>
              <h2 className="flex items-center gap-2 font-semibold text-ink"><MapPin size={17} className="text-brand-purple" aria-hidden />Venue map</h2>
              <p className="mt-1 text-sm text-muted">Select a hotel to see what’s happening there.</p>
            </div>
            <span className="rounded-lg bg-brand-tint px-2.5 py-1 font-mono text-xs font-semibold text-brand-purple">{graph.venues.length - 1} campuses</span>
          </div>
          <div className="overflow-x-auto">
            <div className="amap relative aspect-[16/10] min-w-[680px]" role="group" aria-label="Map of the Las Vegas Strip and re:Invent venues">
              <svg viewBox={`0 0 ${MAP_W} ${MAP_H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
                <defs>
                  <pattern id="amap-blocks" width="70" height="58" patternUnits="userSpaceOnUse" patternTransform={`rotate(${STRIP_TILT})`}>
                    <rect x="5" y="5" width="60" height="48" rx="7" className="amap-block" />
                  </pattern>
                  <path id="amap-strip" d={STRIP_PATH} />
                  <path id="amap-koval" d={KOVAL_PATH} />
                  {CROSS_STREETS.map((street) => <path key={street.name} id={`amap-${street.name.replace(/\s/g, "-")}`} d={street.d} />)}
                  <linearGradient id="amap-route" x1="0" x2="1">
                    <stop offset="0%" stopColor="rgb(var(--c-brand-purple))" />
                    <stop offset="100%" stopColor="rgb(var(--c-brand-orange))" />
                  </linearGradient>
                </defs>
                <rect width={MAP_W} height={MAP_H} className="amap-land" />
                <rect width={MAP_W} height={MAP_H} fill="url(#amap-blocks)" />
                {PARKS.map((d, i) => <path key={i} d={d} className="amap-park" />)}
                {CROSS_STREETS.map((street) => <g key={street.name}><path d={street.d} className="amap-road-edge" strokeWidth="9" /><path d={street.d} className="amap-road" strokeWidth="6" /></g>)}
                <path d={KOVAL_PATH} className="amap-road-edge" strokeWidth="12" /><path d={KOVAL_PATH} className="amap-road" strokeWidth="9" />
                <path d={I15_PATH} className="amap-hwy-edge" strokeWidth="20" /><path d={I15_PATH} className="amap-hwy" strokeWidth="15" />
                <path d={STRIP_PATH} className="amap-road-edge" strokeWidth="30" /><path d={STRIP_PATH} className="amap-road" strokeWidth="25" />
                <path d={STRIP_PATH} className="amap-median" strokeWidth="1.5" />

                {TOP_DOWN_STOPS.map((stop) => {
                  const active = selectedVenue === stop.name || travelFrom === stop.name;
                  const inRoute = routeBlocks.some((block) => block.venue === stop.name);
                  const rx = stop.type === "stadium" ? Math.min(stop.w, stop.h) / 2 : 12;
                  const state = `${active ? "is-active" : ""} ${inRoute ? "is-route" : ""} ${stop.type === "hotel" ? "is-hotel" : ""}`;
                  return <g key={stop.name} transform={`rotate(${STRIP_TILT} ${stop.x} ${stop.y})`}>
                    <rect x={stop.x - stop.w / 2 + 5} y={stop.y - stop.h / 2 + 8} width={stop.w} height={stop.h} rx={rx} className="amap-bldg-shadow" />
                    <rect x={stop.x - stop.w / 2} y={stop.y - stop.h / 2} width={stop.w} height={stop.h} rx={rx} className={`amap-bldg ${state}`} />
                    <rect x={stop.x - stop.w / 2 + 10} y={stop.y - stop.h / 2 + 10} width={stop.w - 20} height={stop.h - 20} rx={Math.max(4, rx - 8)} className="amap-bldg-roof" />
                  </g>;
                })}

                <text className="amap-street-label"><textPath href="#amap-strip" startOffset="9%" dominantBaseline="middle">LAS VEGAS BLVD</textPath></text>
                <text className="amap-street-label"><textPath href="#amap-koval" startOffset="55%" dominantBaseline="middle">KOVAL LN</textPath></text>
                {CROSS_STREETS.map((street) => <text key={street.name} className="amap-street-label"><textPath href={`#amap-${street.name.replace(/\s/g, "-")}`} startOffset="6%" dominantBaseline="middle">{street.name.toUpperCase()}</textPath></text>)}
                <text x="808" y="124" className="amap-area-label">WYNN GOLF CLUB</text>

                {(() => {
                  const from = topDownStop(travelFrom); const to = topDownStop(travelTo);
                  return from && to && from.name !== to.name ? <g>
                    <path d={arcBetween(from, to)} className="amap-line-edge" strokeWidth="11" />
                    <path d={arcBetween(from, to)} stroke="url(#amap-route)" className="amap-line" strokeWidth="6" />
                  </g> : null;
                })()}
                {routeLegs.map((leg) => {
                  const from = topDownStop(leg.from.venue); const to = topDownStop(leg.to.venue);
                  if (!from || !to || from.name === to.name) return null;
                  return <path key={`${leg.from.key}-${leg.to.key}`} d={arcBetween(from, to)} className="amap-route-line" strokeWidth="4" />;
                })}
              </svg>

              {TOP_DOWN_STOPS.map((stop) => {
                const active = selectedVenue === stop.name || travelFrom === stop.name;
                const inRoute = routeBlocks.some((block) => block.venue === stop.name);
                const count = venueCounts.get(stop.name);
                return <button key={stop.name} type="button" aria-pressed={active} aria-label={`${stop.label}${count ? `, ${count.toLocaleString()} sessions` : ""}`}
                  onClick={() => { setTravelFrom(stop.name); if (pointFor(stop.name)) setSelectedVenue(stop.name); if (travelTo === stop.name) setTravelTo(travelFrom); }}
                  style={{ left: pct(stop.x, MAP_W), top: pct(stop.y, MAP_H) }}
                  className={`amap-pin side-${stop.side} ${active ? "is-active" : ""} ${inRoute ? "is-route" : ""} ${stop.type === "hotel" ? "is-hotel" : ""}`}>
                  <span className="amap-pin-marker"><StopIcon type={stop.type} /></span>
                  <span className="amap-pin-label">
                    <span className="amap-pin-name">{stop.label}</span>
                    <span className="amap-pin-meta">{count ? `${count.toLocaleString()} session${count === 1 ? "" : "s"}` : "Nearby"}</span>
                  </span>
                </button>;
              })}

              <div className="amap-compass" aria-hidden><Navigation size={13} strokeWidth={2.25} /><span>N</span></div>

            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-[var(--glass-ring)] px-5 py-4" aria-live="polite">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-tint text-brand-purple"><Navigation size={16} strokeWidth={2.25} aria-hidden /></span>
              <div className="min-w-0">
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[.12em] text-muted">Getting there</p>
                <p className="truncate text-sm font-semibold text-ink">{topDownStop(travelFrom)?.label} <span className="text-muted">→</span></p>
              </div>
            </div>
            <div>
              <label className="sr-only" htmlFor="travel-to">Destination</label>
              <select id="travel-to" value={travelTo} onChange={(e) => setTravelTo(e.target.value)} className="rounded-lg border border-border bg-canvas px-3 py-2 text-sm font-medium text-ink">
                {TOP_DOWN_STOPS.filter((stop) => stop.name !== travelFrom).map((stop) => <option key={stop.name} value={stop.name}>{stop.label}</option>)}
              </select>
            </div>
            <div className="ml-auto flex gap-3">
              <div className="rounded-xl bg-surface px-3.5 py-2"><p className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted"><Footprints size={12} aria-hidden />Walk</p><p className="mt-0.5 font-mono text-sm font-semibold text-ink">{travelWalk} min</p></div>
              <div className="rounded-xl bg-surface px-3.5 py-2"><p className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-muted"><Car size={12} aria-hidden />Rideshare</p><p className="mt-0.5 font-mono text-sm font-semibold text-ink">{rideshareLow}–{rideshareHigh} min</p></div>
            </div>
            <p className="w-full text-[11px] text-muted">Typical estimate. Traffic and pickup time vary.</p>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-[var(--glass-ring)] px-5 py-3 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-brand-purple" />Venue campus</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-brand-orange" />On your route</span>
            <span className="inline-flex items-center gap-1.5"><Route size={14} />Your selected-day journey</span>
          </div>
        </Card>

        <Card glass className="flex flex-col overflow-hidden p-0">
          <div className="border-b border-[var(--glass-ring)] px-5 py-4">
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-brand-purple">Selected venue</p>
            <h2 className="mt-1 text-xl font-semibold text-ink">{pointFor(selectedVenue)?.label ?? selectedVenue}</h2>
            <p className="mt-1 text-sm text-muted">{selectedSessions.length.toLocaleString()} catalog sessions</p>
          </div>
          <div className="flex-1 space-y-3 p-4">
            {selectedSessions.slice(0, 5).map((session) => (
              <Link key={session.id} href={`/session/${encodeURIComponent(session.id)}`} className="block rounded-xl border border-[var(--glass-ring)] bg-canvas/40 p-3 transition hover:border-brand-purple/40 hover:bg-canvas/70">
                <div className="flex items-start justify-between gap-2 font-mono text-xs text-muted"><span className="min-w-0">{dayLabel(session.start)} · {rangeLabel(session.start, session.end)}</span><span className="shrink-0 whitespace-nowrap font-semibold text-brand-purple">{session.code}</span></div>
                <p className="mt-1 text-sm font-semibold leading-snug text-ink">{session.title}</p>
                <p className="mt-1 truncate text-xs text-muted">{session.room || session.type}</p>
              </Link>
            ))}
            {selectedSessions.length > 5 && <Link href={`/catalog`} className="block py-1 text-center text-sm font-semibold text-brand-purple hover:underline">Browse all {selectedSessions.length.toLocaleString()} sessions</Link>}
          </div>
        </Card>
      </div>

      <Card glass className="overflow-hidden p-0">
        {VENUE_PLANS[selectedVenue] ? (
          <VenueIsoPlan key={selectedVenue} venue={pointFor(selectedVenue)?.label ?? selectedVenue} plan={VENUE_PLANS[selectedVenue]} sessions={selectedSessions} reference={referencePlan} />
        ) : (
          <div className="p-5">
            <h2 className="font-semibold text-ink">Session space directory</h2>
            <p className="mt-1 text-sm text-muted">No verified public floor plan is available for this venue yet.</p>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">{selectedRooms.map(([room, count]) => <div key={room} className="rounded-lg border border-border bg-canvas/70 p-2.5"><p className="line-clamp-2 text-xs font-semibold leading-snug text-ink">{room}</p><p className="mt-1 font-mono text-xs text-muted">{count} session{count === 1 ? "" : "s"}</p></div>)}</div>
          </div>
        )}
      </Card>

      <Card glass className="overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--glass-ring)] px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 font-semibold text-ink"><Route size={17} className="text-brand-purple" aria-hidden />Your route, day by day</h2>
            <p className="mt-1 text-sm text-muted">Built from the sessions and custom blocks in your Stack.</p>
          </div>
          {routeDays.length > 0 && <Segmented ariaLabel="Select a route day" value={activeDay} onChange={setSelectedDay} options={routeDays.map((day) => ({ value: day, label: dayLabel(day) }))} />}
        </div>
        {routeBlocks.length === 0 ? (
          <div className="p-6"><EmptyState icon={Sparkles} title="Build a route from your stack" body="Add sessions to your Stack and we’ll draw your venue-to-venue journey here." action={<Link href="/plan" className="inline-flex rounded-lg bg-brand px-3.5 py-2 text-sm font-semibold text-white">Plan my week</Link>} /></div>
        ) : (
          <div className="grid gap-0 lg:grid-cols-[1fr_300px]">
            <ol className="divide-y divide-[var(--glass-ring)] p-3 sm:p-5">
              {routeBlocks.map((block, index) => {
                const leg = index > 0 ? routeLegs[index - 1] : null;
                return <li key={block.key} className="relative py-3 pl-10 first:pt-0 last:pb-0">
                  <span className="absolute left-0 top-4 flex h-7 w-7 items-center justify-center rounded-full bg-brand-tint font-mono text-xs font-semibold text-brand-purple">{index + 1}</span>
                  {leg && <p className="mb-2 inline-flex items-center gap-1.5 rounded-md bg-surface px-2 py-1 font-mono text-xs text-muted"><Clock3 size={13} />{leg.minutes == null ? "Walk unknown" : `${leg.minutes} min walk from ${leg.from.venue}`}</p>}
                  <p className="font-mono text-xs text-muted">{rangeLabel(block.start, block.end)} · {block.venue}</p>
                  <p className="mt-1 font-semibold text-ink">{block.title}</p>
                  {block.room && <p className="mt-1 text-xs text-muted">{block.room}</p>}
                </li>;
              })}
            </ol>
            <div className="border-t border-[var(--glass-ring)] bg-canvas/25 p-5 lg:border-l lg:border-t-0">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-brand-purple">Route summary</p>
              <p className="mt-3 text-3xl font-semibold text-ink">{routeLegs.reduce((total, leg) => total + (leg.minutes ?? 0), 0)} <span className="text-base font-medium text-muted">min walking</span></p>
              <p className="mt-1 text-sm text-muted">Across {routeLegs.filter((leg) => leg.minutes !== null && leg.minutes > 0).length} venue change{routeLegs.filter((leg) => leg.minutes !== null && leg.minutes > 0).length === 1 ? "" : "s"}.</p>
              <div className="mt-5 rounded-xl border border-[var(--glass-ring)] bg-canvas/50 p-3 text-sm text-muted">Allow about 10 minutes of extra buffer on top of each walk for elevators, crowds, and finding your room.</div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
