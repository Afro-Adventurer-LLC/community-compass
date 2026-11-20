"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "bc-theme";

/** Icon button that toggles the navy dark theme and remembers the choice. */
export default function ThemeToggle({ withLabel = false }: { withLabel?: boolean }) {
  const [dark, setDark] = useState(false);

  // The no-flash script in layout.tsx already set the class; sync state to it.
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      /* storage unavailable; theme still applies for this visit */
    }
  }

  const Icon = dark ? Sun : Moon;
  const label = dark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted transition duration-200 hover:bg-surface hover:text-ink ${
        withLabel ? "w-full" : "justify-center"
      }`}
    >
      <Icon size={18} strokeWidth={1.75} aria-hidden />
      {withLabel && <span>{dark ? "Light mode" : "Dark mode"}</span>}
    </button>
  );
}
