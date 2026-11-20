"use client";

import { useEffect } from "react";
import { useCompassStore } from "@/lib/store";

// Loads saved plan/profile from localStorage after the first render, so the
// server HTML and the first client render always match.
export default function StoreHydrator() {
  useEffect(() => {
    Promise.resolve(useCompassStore.persist.rehydrate()).finally(() => {
      useCompassStore.setState({ hydrated: true });
    });
  }, []);
  return null;
}
