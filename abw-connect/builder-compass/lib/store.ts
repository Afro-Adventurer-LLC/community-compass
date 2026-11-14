// ---------------------------------------------------------------------------
// Global client state for Builder Compass.
// Guest-first: everything persists to localStorage. No account, no server.
// When the AWS backend arrives, this store can hydrate from / sync to it.
//
// Hydration is manual (skipHydration) so the first client render matches the
// server HTML. <StoreHydrator /> loads saved data after mount and flips
// `hydrated`; pages that show saved data wait for it.
// ---------------------------------------------------------------------------

"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  CustomItem,
  PlanItem,
  PlanStatus,
  SessionRating,
  UserPrefs,
} from "@/types";

interface PersistedState {
  plan: PlanItem[];
  customItems: CustomItem[];
  prefs: UserPrefs;
  // Notes and ratings of sessions taken out of the stack, keyed by session id.
  // Removing a session never deletes what you wrote; re-adding restores it.
  archive: Record<string, PlanItem>;
}

/** The most recent removal, so it can be undone. Not persisted. */
export type RemovedEntry =
  | { kind: "session"; item: PlanItem; index: number; at: number }
  | { kind: "custom"; item: CustomItem; index: number; at: number };

export function hasWriting(item: PlanItem): boolean {
  const r = item.rating;
  return !!(
    item.note?.text?.trim() ||
    (r &&
      (r.value > 0 ||
        r.wouldRecommend !== undefined ||
        r.takeaway?.trim() ||
        r.actionItems?.trim()))
  );
}

interface CompassState extends PersistedState {
  hydrated: boolean;
  lastRemoved: RemovedEntry | null;

  // plan actions
  addToPlan: (sessionId: string, status?: PlanStatus) => void;
  addManyToPlan: (sessionIds: string[]) => void;
  removeFromPlan: (sessionId: string) => void;
  isPlanned: (sessionId: string) => boolean;
  setStatus: (sessionId: string, status: PlanStatus) => void;
  setNote: (sessionId: string, text: string) => void;
  patchRating: (sessionId: string, patch: Partial<SessionRating>) => void;

  // custom items
  addCustomItem: (item: Omit<CustomItem, "id">) => void;
  removeCustomItem: (id: string) => void;

  // profile
  setPrefs: (patch: Partial<UserPrefs>) => void;

  // undo
  undoRemove: () => void;
  dismissUndo: () => void;

  // utility
  clearAll: () => void;
}

const defaultPrefs: UserPrefs = {
  interests: ["artificial intelligence", "developer tools", "serverless"],
  depth: 300,
  role: "Developer / Engineer",
  days: [],
  includeEvents: false,
  maxPerDay: 5,
  goal: "",
};

function newPlanItem(sessionId: string, status: PlanStatus = "planned"): PlanItem {
  return { sessionId, status, addedAt: new Date().toISOString() };
}

/** A fresh plan item that brings back any archived notes and rating. */
function restoredItem(
  archive: Record<string, PlanItem>,
  sessionId: string,
  status: PlanStatus = "planned"
): PlanItem {
  const saved = archive[sessionId];
  const item = newPlanItem(sessionId, status);
  return saved ? { ...item, note: saved.note, rating: saved.rating } : item;
}

function without<T>(record: Record<string, T>, keys: string[]): Record<string, T> {
  if (!keys.some((k) => k in record)) return record;
  const next = { ...record };
  for (const k of keys) delete next[k];
  return next;
}

export const useCompassStore = create<CompassState>()(
  persist(
    (set, get) => ({
      hydrated: false,
      lastRemoved: null,
      plan: [],
      customItems: [],
      prefs: defaultPrefs,
      archive: {},

      addToPlan: (sessionId, status = "planned") =>
        set((state) =>
          state.plan.some((p) => p.sessionId === sessionId)
            ? state
            : {
                plan: [...state.plan, restoredItem(state.archive, sessionId, status)],
                archive: without(state.archive, [sessionId]),
              }
        ),

      addManyToPlan: (sessionIds) =>
        set((state) => {
          const have = new Set(state.plan.map((p) => p.sessionId));
          const ids = Array.from(new Set(sessionIds)).filter((id) => !have.has(id));
          if (ids.length === 0) return state;
          return {
            plan: [...state.plan, ...ids.map((id) => restoredItem(state.archive, id))],
            archive: without(state.archive, ids),
          };
        }),

      removeFromPlan: (sessionId) =>
        set((state) => {
          const index = state.plan.findIndex((p) => p.sessionId === sessionId);
          if (index === -1) return state;
          const item = state.plan[index];
          return {
            plan: state.plan.filter((p) => p.sessionId !== sessionId),
            archive: hasWriting(item)
              ? { ...state.archive, [sessionId]: item }
              : state.archive,
            lastRemoved: { kind: "session", item, index, at: Date.now() },
          };
        }),

      isPlanned: (sessionId) =>
        get().plan.some((p) => p.sessionId === sessionId),

      setStatus: (sessionId, status) =>
        set((state) => ({
          plan: state.plan.map((p) =>
            p.sessionId === sessionId ? { ...p, status } : p
          ),
        })),

      setNote: (sessionId, text) =>
        set((state) => ({
          plan: state.plan.map((p) =>
            p.sessionId === sessionId
              ? { ...p, note: { text, updatedAt: new Date().toISOString() } }
              : p
          ),
        })),

      patchRating: (sessionId, patch) =>
        set((state) => ({
          plan: state.plan.map((p) =>
            p.sessionId === sessionId
              ? { ...p, rating: { value: 0, ...p.rating, ...patch } }
              : p
          ),
        })),

      addCustomItem: (item) =>
        set((state) => ({
          customItems: [
            ...state.customItems,
            {
              ...item,
              id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            },
          ],
        })),

      removeCustomItem: (id) =>
        set((state) => {
          const index = state.customItems.findIndex((c) => c.id === id);
          if (index === -1) return state;
          return {
            customItems: state.customItems.filter((c) => c.id !== id),
            lastRemoved: {
              kind: "custom",
              item: state.customItems[index],
              index,
              at: Date.now(),
            },
          };
        }),

      undoRemove: () =>
        set((state) => {
          const last = state.lastRemoved;
          if (!last) return state;
          if (last.kind === "session") {
            const id = last.item.sessionId;
            if (state.plan.some((p) => p.sessionId === id)) {
              return { lastRemoved: null };
            }
            const plan = [...state.plan];
            plan.splice(Math.min(last.index, plan.length), 0, last.item);
            return { plan, archive: without(state.archive, [id]), lastRemoved: null };
          }
          if (state.customItems.some((c) => c.id === last.item.id)) {
            return { lastRemoved: null };
          }
          const customItems = [...state.customItems];
          customItems.splice(Math.min(last.index, customItems.length), 0, last.item);
          return { customItems, lastRemoved: null };
        }),

      dismissUndo: () => set({ lastRemoved: null }),

      setPrefs: (patch) =>
        set((state) => ({ prefs: { ...state.prefs, ...patch } })),

      // Keeps notes: anything written is moved to the archive first.
      clearAll: () =>
        set((state) => {
          const archive = { ...state.archive };
          for (const p of state.plan) if (hasWriting(p)) archive[p.sessionId] = p;
          return { plan: [], customItems: [], archive, lastRemoved: null };
        }),
    }),
    {
      name: "builder-compass-v2",
      skipHydration: true,
      partialize: (s): PersistedState => ({
        plan: s.plan,
        customItems: s.customItems,
        prefs: s.prefs,
        archive: s.archive,
      }),
      // Newer preference fields fall back to defaults for older saved data.
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<PersistedState>;
        return {
          ...current,
          plan: saved.plan ?? current.plan,
          customItems: saved.customItems ?? current.customItems,
          prefs: { ...current.prefs, ...(saved.prefs ?? {}) },
          archive: saved.archive ?? current.archive,
        };
      },
    }
  )
);

/** True once saved data has been loaded from localStorage. */
export function useHydrated(): boolean {
  return useCompassStore((s) => s.hydrated);
}
