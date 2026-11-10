import Link from "next/link";
import {
  ArrowRight,
  Bot,
  CalendarCheck,
  NotebookPen,
  Footprints,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { buttonClass } from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import CompassMark from "@/components/CompassMark";
import { loadSessions } from "@/lib/data.server";
import { dateOf } from "@/lib/format";

const FEATURES = [
  {
    icon: Search,
    title: "Search the whole catalog",
    body: "Filter by day, track, role, level, and venue, or ask in a plain sentence and see exactly how it was read.",
  },
  {
    icon: Sparkles,
    title: "Plan my week",
    body: "Get a draft week from your role, depth, and interests, with a theme for each day. Add it all in one click.",
  },
  {
    icon: Footprints,
    title: "Know you can get there",
    body: "Venues are kilometres apart. Every block shows the walk from the one before and whether you can make it.",
  },
  {
    icon: CalendarCheck,
    title: "Fill the gaps",
    body: "Free time between sessions comes with reachable suggestions, ranked for you. Export the week to your calendar.",
  },
  {
    icon: Bot,
    title: "Use your own AI",
    body: "Copy a ready-made prompt into the assistant you trust and paste its reply back. Nothing leaves your browser.",
  },
  {
    icon: NotebookPen,
    title: "Take notes, leave with a report",
    body: "Rate each session, capture the takeaway and action items, and export a trip report as Markdown.",
  },
];

export default function HomePage() {
  const sessions = loadSessions();
  const venues = new Set(sessions.map((s) => s.venue)).size;
  const days = new Set(sessions.map((s) => dateOf(s.start))).size;

  const stats = [
    { value: sessions.length.toLocaleString(), label: "sessions" },
    { value: String(days), label: "days" },
    { value: String(venues), label: "venues" },
  ];

  return (
    <div className="space-y-10">
      <section className="rounded-2xl border border-border bg-canvas px-6 py-10 shadow-card md:px-12 md:py-14">
        <div>
          <div>
            <div className="mb-8 flex items-center gap-5">
              <CompassMark size={96} />
              <div>
                <p className="text-3xl leading-none tracking-tight md:text-4xl">
                  <span className="font-bold text-ink">Builder</span>{" "}
                  <span className="font-medium text-muted">Compass</span>
                </p>
                <p className="mt-2 font-mono text-sm text-muted">
                  AWS re:Invent 2026
                </p>
              </div>
            </div>

            <h1 className="mb-4 max-w-2xl text-4xl font-bold leading-tight tracking-tight text-ink md:text-5xl">
              Plan your re:Invent week so it{" "}
              <span className="bg-brand bg-clip-text text-transparent">
                actually fits.
              </span>
            </h1>
            <p className="mb-8 max-w-xl text-lg leading-relaxed text-muted">
              Find the right sessions and build a schedule that never sends you
              across the Strip in twenty minutes. Everything runs in your
              browser. No account, no tracking.
            </p>

            <div className="mb-8 flex flex-wrap gap-3">
              <Link href="/plan" className={buttonClass("primary", "px-5 py-2.5")}>
                Plan my week
                <ArrowRight size={16} strokeWidth={2} aria-hidden />
              </Link>
              <Link
                href="/catalog"
                className={buttonClass("secondary", "px-5 py-2.5")}
              >
                Browse the catalog
              </Link>
            </div>

            <dl className="flex gap-8 border-t border-border pt-6">
              {stats.map((s) => (
                <div key={s.label}>
                  <dt className="sr-only">{s.label}</dt>
                  <dd className="text-sm text-muted">
                    <span className="block font-mono text-2xl font-semibold text-ink">
                      {s.value}
                    </span>
                    {s.label}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

        </div>
      </section>

      <section
        aria-label="What you can do"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {FEATURES.map(({ icon: Icon, title, body }) => (
          <Card
            key={title}
            className="transition duration-200 hover:border-border-strong"
          >
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-brand-tint text-brand-purple">
              <Icon size={20} strokeWidth={1.75} aria-hidden />
            </div>
            <h2 className="mb-1.5 font-semibold text-ink">{title}</h2>
            <p className="text-sm leading-relaxed text-muted">{body}</p>
          </Card>
        ))}
      </section>

      <p className="flex items-start gap-2 px-1 text-xs leading-relaxed text-muted">
        <ShieldCheck size={14} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden />
        Independent, unofficial planner. Not affiliated with or endorsed by AWS.
      </p>
    </div>
  );
}
