// ---------------------------------------------------------------------------
// Catalog view state (filters, sort, sentence search). Kept in a tiny store so
// it survives navigating to a session and back — "preserve user selections".
// In-memory only: a full page reload starts fresh.
// ---------------------------------------------------------------------------

"use client";

import { create } from "zustand";
import { emptyFilters, type Filters } from "@/lib/search";

// relevance: best text match while searching, otherwise ranked for your profile
export type SortKey = "relevance" | "time" | "title";

interface CatalogViewState {
  filters: Filters;
  sort: SortKey;
  nlQuery: string;
  nlExplanation: string | null;
  setFilters: (filters: Filters) => void;
  setSort: (sort: SortKey) => void;
  setNl: (query: string, explanation: string | null) => void;
  reset: () => void;
}

export const useCatalogView = create<CatalogViewState>()((set) => ({
  filters: emptyFilters,
  sort: "relevance",
  nlQuery: "",
  nlExplanation: null,
  setFilters: (filters) => set({ filters }),
  setSort: (sort) => set({ sort }),
  setNl: (nlQuery, nlExplanation) => set({ nlQuery, nlExplanation }),
  reset: () => set({ filters: emptyFilters, nlQuery: "", nlExplanation: null }),
}));
