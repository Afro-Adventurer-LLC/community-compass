"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarCheck,
  NotebookPen,
  House,
  LayoutGrid,
  MapPin,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useCompassStore, useHydrated } from "@/lib/store";
import ThemeToggle from "@/components/ThemeToggle";

const LINKS: {
  href: string;
  label: string;
  icon: LucideIcon;
  also?: string[]; // other paths that belong to this section
}[] = [
  { href: "/", label: "Home", icon: House },
  { href: "/catalog", label: "Catalog", icon: LayoutGrid, also: ["/session"] },
  { href: "/plan", label: "Plan my week", icon: Sparkles },
  { href: "/stack", label: "Your Stack", icon: CalendarCheck },
  { href: "/map", label: "Venues", icon: MapPin },
  { href: "/notes", label: "Notes", icon: NotebookPen },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <Image
        src="/icon.svg"
        alt=""
        width={36}
        height={36}
        unoptimized
        className="rounded-[10px]"
      />
      <span className="text-[15px] leading-tight tracking-tight">
        <span className="font-bold text-ink">Builder</span>{" "}
        <span className="font-medium text-muted">Compass</span>
      </span>
    </Link>
  );
}

function useNavItems() {
  const pathname = usePathname();
  const hydrated = useHydrated();
  // Matches the "blocks planned" count on the stack page (sessions + custom).
  const planCount = useCompassStore((s) => s.plan.length + s.customItems.length);
  return LINKS.map((link) => {
    const paths = [link.href, ...(link.also ?? [])];
    const active =
      link.href === "/"
        ? pathname === "/"
        : paths.some((p) => pathname === p || pathname.startsWith(`${p}/`));
    return {
      ...link,
      active,
      // Wait for saved data so the count never flashes 0 then jumps.
      count: link.href === "/stack" && hydrated ? planCount : 0,
    };
  });
}

export default function Sidebar() {
  const items = useNavItems();

  return (
    <>
      {/* Desktop / tablet: persistent sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-canvas dark:bg-canvas/80 dark:backdrop-blur-xl px-4 py-5 md:flex">
        <Brand />
        <nav aria-label="Main" className="mt-8 flex flex-col gap-1">
          {items.map(({ href, label, icon: Icon, active, count }) => (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition duration-200 ${
                active
                  ? "bg-brand-tint text-brand-purple"
                  : "text-muted hover:bg-surface hover:text-ink"
              }`}
            >
              <Icon size={18} strokeWidth={1.75} aria-hidden />
              <span className="flex-1">{label}</span>
              {count > 0 && (
                <span className="rounded-md bg-brand-purple px-1.5 py-0.5 font-mono text-xs text-white dark:text-code">
                  {count}
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="mt-auto">
          <ThemeToggle withLabel />
        </div>
      </aside>

      {/* Mobile: compact top bar with horizontally scrollable nav */}
      <header className="sticky top-0 z-40 border-b border-border bg-canvas dark:bg-canvas/80 dark:backdrop-blur-xl md:hidden">
        <div className="flex items-center justify-between px-4 pt-3">
          <Brand />
          <ThemeToggle />
        </div>
        <nav
          aria-label="Main"
          className="flex gap-1 overflow-x-auto px-3 pb-2 pt-2"
        >
          {items.map(({ href, label, icon: Icon, active, count }) => (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-[44px] shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium transition duration-200 ${
                active
                  ? "bg-brand-tint text-brand-purple"
                  : "text-muted hover:bg-surface hover:text-ink"
              }`}
            >
              <Icon size={16} strokeWidth={1.75} aria-hidden />
              {label}
              {count > 0 && (
                <span className="rounded-md bg-brand-purple px-1.5 py-0.5 font-mono text-xs text-white dark:text-code">
                  {count}
                </span>
              )}
            </Link>
          ))}
        </nav>
      </header>
    </>
  );
}
