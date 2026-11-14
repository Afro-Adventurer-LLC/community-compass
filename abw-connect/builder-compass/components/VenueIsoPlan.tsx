"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Box, Layers } from "lucide-react";
import type { Session } from "@/types";
import type { PlanLevel, PlanRoom, VenuePlan } from "@/lib/venuePlans";
import { rangeLabel, dayLabel } from "@/lib/format";
import Segmented from "@/components/ui/Segmented";

// Isometric projection: plan x runs up-right, plan y runs down-right, z is up.
const COS = 0.866;
const SIN = 0.5;
const PLATE = 2; // slab thickness
const ROOM_H = 2.8; // default room extrusion
const LIFT = 2.2; // hover lift
const GAP = 34; // exploded spacing between levels
const MARGIN = 2.5; // slab overhang past the rooms
const EXPLODED = "all";

type Pt = [number, number, number];

export default function VenueIsoPlan({
  venue,
  plan,
  sessions,
  reference,
}: {
  venue: string;
  plan: VenuePlan;
  sessions: Session[];
  reference?: { image: string; title: string; source: string };
}) {
  const multi = plan.levels.length > 1;
  const [focus, setFocus] = useState<string>(multi ? EXPLODED : plan.levels[0].id);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const exploded = multi && focus === EXPLODED;
  const scale = exploded ? 3.3 : 6;
  const visible: PlanLevel[] = exploded ? plan.levels : plan.levels.filter((l) => l.id === focus);

  // Sessions per room — the first room whose fragments match wins.
  const { byRoom, unmapped } = useMemo(() => {
    const map = new Map<string, Session[]>();
    const rooms = plan.levels.flatMap((l) => l.rooms);
    let missed = 0;
    for (const s of sessions) {
      const hay = (s.room || "").toLowerCase();
      const hit = hay ? rooms.find((rm) => rm.match?.some((m) => hay.includes(m))) : undefined;
      if (!hit) { missed += 1; continue; }
      map.set(hit.id, [...(map.get(hit.id) ?? []), s]);
    }
    map.forEach((list) => list.sort((a, b) => a.start.localeCompare(b.start)));
    return { byRoom: map, unmapped: missed };
  }, [plan, sessions]);

  const levelOf = (roomId: string) => plan.levels.find((l) => l.rooms.some((rm) => rm.id === roomId));
  const activeId = hovered ?? selected;
  const activeRoom = activeId ? plan.levels.flatMap((l) => l.rooms).find((rm) => rm.id === activeId) : undefined;
  const activeSessions = activeRoom ? byRoom.get(activeRoom.id) ?? [] : [];

  const P = (x: number, y: number, z: number): [number, number] => [
    (x + y) * COS * scale,
    (y - x) * SIN * scale - z * scale,
  ];
  const poly = (pts: Pt[]) => pts.map(([x, y, z]) => P(x, y, z).map((n) => n.toFixed(1)).join(",")).join(" ");

  // Faces of an axis-aligned box. Visible: top, front-right (y max), front-left (x min).
  const box = (x: number, y: number, w: number, d: number, z0: number, h: number) => {
    const t = z0 + h;
    return {
      top: poly([[x, y, t], [x + w, y, t], [x + w, y + d, t], [x, y + d, t]]),
      right: poly([[x, y + d, t], [x + w, y + d, t], [x + w, y + d, z0], [x, y + d, z0]]),
      left: poly([[x, y, t], [x, y + d, t], [x, y + d, z0], [x, y, z0]]),
    };
  };

  // Canvas bounds from every visible slab corner.
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  visible.forEach((level, i) => {
    const z0 = exploded ? i * GAP : 0;
    const [w, d] = level.size;
    const ox = level.ox ?? 0;
    for (const x of [ox - MARGIN, ox + w + MARGIN]) {
      for (const y of [-MARGIN, d + MARGIN]) {
        for (const z of [z0 - 1, z0 + PLATE + ROOM_H + LIFT]) {
          const [sx, sy] = P(x, y, z);
          minX = Math.min(minX, sx); maxX = Math.max(maxX, sx);
          minY = Math.min(minY, sy); maxY = Math.max(maxY, sy);
        }
      }
    }
  });
  const pad = 28;
  const extraRight = exploded ? 84 : 0;
  const vb = `${(minX - pad).toFixed(0)} ${(minY - pad).toFixed(0)} ${(maxX - minX + pad * 2 + extraRight).toFixed(0)} ${(maxY - minY + pad * 2).toFixed(0)}`;

  const tabs = [
    ...(multi ? [{ value: EXPLODED, label: "All levels" }] : []),
    ...plan.levels.map((l) => ({ value: l.id, label: l.tab })),
  ];

  const pick = (room: PlanRoom, levelId: string) => {
    setSelected((cur) => (cur === room.id ? null : room.id));
    if (exploded) setFocus(levelId);
  };

  const renderRoom = (room: PlanRoom, level: PlanLevel, z0: number) => {
    const ox = level.ox ?? 0;
    const active = activeId === room.id;
    const dim = !!activeId && !active;
    const h = room.h ?? ROOM_H;
    const faces = box(ox + room.x, room.y, room.w, room.d, z0 + PLATE, h);
    const count = byRoom.get(room.id)?.length ?? 0;
    const top = z0 + PLATE + h;
    const [cx, cy] = P(ox + room.x + room.w / 2, room.y + room.d / 2, top);
    const fs = Math.min(3.2, (room.w * 0.86) / (room.name.length * 0.58), room.d * 0.42);
    const showText = !exploded && fs >= 1.35;
    const m = `matrix(${(COS * scale).toFixed(3)} ${(-SIN * scale).toFixed(3)} ${(COS * scale).toFixed(3)} ${(SIN * scale).toFixed(3)} ${cx.toFixed(1)} ${cy.toFixed(1)})`;
    return (
      <g
        key={room.id}
        className="iso-room-wrap"
        tabIndex={0}
        role="button"
        aria-pressed={selected === room.id}
        aria-label={`${room.name}, ${count} session${count === 1 ? "" : "s"}`}
        onMouseEnter={() => setHovered(room.id)}
        onMouseLeave={() => setHovered(null)}
        onFocus={() => setHovered(room.id)}
        onBlur={() => setHovered(null)}
        onClick={() => pick(room, level.id)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(room, level.id); } }}
      >
        <g
          className={`iso-room iso-t-${room.tone} ${active ? "is-active" : ""} ${dim ? "is-dim" : ""}`}
          style={{ transform: active ? `translateY(${(-LIFT * scale).toFixed(1)}px)` : undefined }}
        >
          <polygon points={faces.left} className="iso-side-l" />
          <polygon points={faces.right} className="iso-side-r" />
          <polygon points={faces.top} className="iso-top" />
          {showText && (
            <g transform={m} className="iso-text" pointerEvents="none">
              <text x="0" y={count > 0 && fs >= 2 ? -fs * 0.18 : 0} fontSize={fs} textAnchor="middle" dominantBaseline="central" className="iso-name">{room.name}</text>
              {count > 0 && fs >= 2 && <text x="0" y={fs * 0.82} fontSize={fs * 0.62} textAnchor="middle" dominantBaseline="central" className="iso-meta">{count} session{count === 1 ? "" : "s"}</text>}
            </g>
          )}
        </g>
        {/* Stays put while the room lifts, so the pointer never "falls off". */}
        <polygon points={faces.top} fill="transparent" />
      </g>
    );
  };

  const renderLevel = (level: PlanLevel, index: number) => {
    const z0 = exploded ? index * GAP : 0;
    const [w, d] = level.size;
    const ox = level.ox ?? 0;
    const slab = box(ox - MARGIN, -MARGIN, w + MARGIN * 2, d + MARGIN * 2, z0, PLATE);
    const shadow = poly([
      [ox - MARGIN + 2, -MARGIN + 2, z0 - 1], [ox + w + MARGIN + 2, -MARGIN + 2, z0 - 1],
      [ox + w + MARGIN + 2, d + MARGIN + 2, z0 - 1], [ox - MARGIN + 2, d + MARGIN + 2, z0 - 1],
    ]);
    // Painter's order: furthest (up-right, back) first.
    const rooms = [...level.rooms].sort((a, b) => (b.x + b.w / 2 - b.y - b.d / 2) - (a.x + a.w / 2 - a.y - a.d / 2));
    const [lx, ly] = P(ox + w + MARGIN, d + MARGIN, z0 + PLATE);
    const dimmed = exploded && !!activeRoom && levelOf(activeRoom.id)?.id !== level.id;
    return (
      <g key={level.id} className={dimmed ? "iso-level-dim" : ""}>
        <polygon points={shadow} className="iso-shadow" filter="url(#iso-blur)" />
        <polygon points={slab.left} className="iso-slab-l" />
        <polygon points={slab.right} className="iso-slab-r" />
        <polygon points={slab.top} className="iso-slab-top" />
        {rooms.map((room) => renderRoom(room, level, z0))}
        {exploded && (
          <g className="iso-level-label" onClick={() => setFocus(level.id)} role="button" tabIndex={0} aria-label={`Focus ${level.label}`}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setFocus(level.id); } }}>
            <line x1={lx + 4} y1={ly} x2={lx + 20} y2={ly} />
            <text x={lx + 26} y={ly} dominantBaseline="central">{level.tab.toUpperCase()}</text>
          </g>
        )}
      </g>
    );
  };

  const focusLevels = exploded ? plan.levels : visible;
  const mapped = sessions.length - unmapped;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--glass-ring)] px-5 py-4">
        <div>
          <h2 className="flex items-center gap-2 font-semibold text-ink"><Box size={17} className="text-brand-purple" aria-hidden />{venue} · venue plan</h2>
          <p className="mt-1 text-sm text-muted">{plan.note}. Hover or tap a room to see what’s on.</p>
        </div>
        <Segmented ariaLabel="Choose a level" value={focus} onChange={(v) => { setFocus(v); setSelected(null); }} options={tabs} />
      </div>

      <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_330px]">
        <div className="iso-stage relative flex items-center justify-center p-4 sm:p-6">
          <svg key={`${venue}-${focus}`} viewBox={vb} className="iso-svg h-auto max-h-[680px] w-full" role="group" aria-label={`Isometric plan of ${venue}`}>
            <defs><filter id="iso-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="9" /></filter></defs>
            {visible.map((level, i) => renderLevel(level, i))}
          </svg>
          {!multi && <span className="iso-badge"><Layers size={12} aria-hidden />Simplified plan</span>}
        </div>

        <aside className="flex flex-col border-t border-[var(--glass-ring)] lg:border-l lg:border-t-0">
          <div className="h-[264px] shrink-0 overflow-hidden border-b border-[var(--glass-ring)] p-5" aria-live="polite">
            {activeRoom ? (
              <>
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[.14em] text-brand-purple">{levelOf(activeRoom.id)?.tab}</p>
                <h3 className="mt-1 line-clamp-2 text-lg font-semibold leading-tight text-ink">{activeRoom.name}</h3>
                <p className="mt-1 text-sm text-muted">{activeSessions.length === 0 ? "No catalog sessions listed here." : `${activeSessions.length} catalog session${activeSessions.length === 1 ? "" : "s"}`}</p>
                <ul className="mt-3 space-y-2">
                  {activeSessions.slice(0, 2).map((s) => (
                    <li key={s.id}>
                      <Link href={`/session/${encodeURIComponent(s.id)}`} className="block rounded-lg border border-[var(--glass-ring)] bg-canvas/50 px-3 py-2 transition hover:border-brand-purple/40">
                        <span className="flex justify-between gap-2 font-mono text-[11px] text-muted"><span>{dayLabel(s.start)} · {rangeLabel(s.start, s.end)}</span><span className="font-semibold text-brand-purple">{s.code}</span></span>
                        <span className="mt-0.5 block truncate text-sm font-medium text-ink">{s.title}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
                {activeSessions.length > 2 && <p className="mt-2 text-xs text-muted">+{activeSessions.length - 2} more in the catalog</p>}
              </>
            ) : (
              <>
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[.14em] text-brand-purple">{exploded ? "All levels" : visible[0].tab}</p>
                <h3 className="mt-1 line-clamp-2 text-lg font-semibold leading-tight text-ink">{exploded ? `${plan.levels.length} levels, stacked` : visible[0].label}</h3>
                <p className="mt-1 text-sm text-muted">{mapped.toLocaleString()} of {sessions.length.toLocaleString()} sessions sit in rooms shown here{unmapped > 0 ? `; ${unmapped.toLocaleString()} are in foyers, booths, or spaces not drawn.` : "."}</p>
              </>
            )}
          </div>

          <div className="h-[296px] shrink-0 overflow-y-auto overscroll-contain p-3">
            {focusLevels.map((level) => (
              <div key={level.id} className="mb-2 last:mb-0">
                {focusLevels.length > 1 && <p className="px-2 pb-1 pt-2 font-mono text-[10px] font-semibold uppercase tracking-[.12em] text-muted">{level.label}</p>}
                <ul>
                  {level.rooms.map((room) => {
                    const n = byRoom.get(room.id)?.length ?? 0;
                    const on = activeId === room.id;
                    return (
                      <li key={room.id}>
                        <button type="button" onClick={() => pick(room, level.id)} onMouseEnter={() => setHovered(room.id)} onMouseLeave={() => setHovered(null)}
                          className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm transition duration-200 ${on ? "bg-brand-tint text-brand-purple" : "text-ink hover:bg-surface"}`}>
                          <span className={`iso-swatch iso-t-${room.tone}`} aria-hidden />
                          <span className="min-w-0 flex-1 truncate font-medium">{room.name}</span>
                          <span className={`font-mono text-xs ${n ? "text-muted" : "text-muted/60"}`}>{n}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--glass-ring)] px-5 py-3 text-xs text-muted">
        <span>Layouts condensed from published floor plans. Not to scale.</span>
        {reference && (
          <a href={reference.source} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-brand-purple hover:underline">Official floor plan<ArrowUpRight size={13} aria-hidden /></a>
        )}
      </div>
      {reference && (
        <details className="venue-source-detail border-t border-[var(--glass-ring)] px-5 py-3">
          <summary>See original reference plan</summary>
          <div className="venue-source-zoom mt-3"><Image src={reference.image} alt={reference.title} width={0} height={0} sizes="100vw" unoptimized className="venue-reference-plan" /></div>
        </details>
      )}
    </div>
  );
}
