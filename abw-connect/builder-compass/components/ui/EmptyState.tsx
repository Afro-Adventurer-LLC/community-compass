import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

// Empty, loading, and error states: say what happened and what to do next.
export default function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  tone = "neutral",
}: {
  icon: LucideIcon;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "error";
}) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className="flex flex-col items-center rounded-2xl border border-dashed border-border-strong bg-canvas px-6 py-14 text-center"
    >
      <Icon
        size={28}
        strokeWidth={1.5}
        className={`mb-3 ${tone === "error" ? "text-error" : "text-muted"}`}
        aria-hidden
      />
      <p className="font-medium text-ink">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
