import type { FeasibilityResult } from "@/types";
import { worstWalk, type Block, type FitResult } from "@/lib/schedule";

// Signature component: dot + label + minutes, tinted by state.
// Status colours are semantic only (reachable / tight / not reachable).
const STYLES: Record<string, { label: string; pill: string; dot: string }> = {
  comfortable: {
    label: "Reachable",
    pill: "bg-success/10 text-success-fg",
    dot: "bg-success",
  },
  tight: {
    label: "Tight",
    pill: "bg-warning/10 text-warning-fg",
    dot: "bg-warning",
  },
  "not-happening": {
    label: "Not reachable",
    pill: "bg-error/10 text-error-fg",
    dot: "bg-error",
  },
  unknown: {
    label: "Walk unknown",
    pill: "bg-surface text-muted",
    dot: "bg-muted",
  },
};

const PILL = "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium";

function shorten(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function otherLabel(b: Block): string {
  return b.code ?? shorten(b.title);
}

export default function FeasibilityBadge({
  result,
  relativeTo,
}: {
  result: FeasibilityResult;
  relativeTo?: { direction: "from" | "to"; block: Block };
}) {
  const style = STYLES[result.feasibility] ?? STYLES.unknown;
  let detail: string;
  if (result.walkMinutes == null) detail = "no route data";
  else if (result.walkMinutes === 0) detail = "same venue";
  else detail = `${result.walkMinutes} min walk`;
  if (relativeTo) {
    const other = otherLabel(relativeTo.block);
    detail =
      result.walkMinutes === 0
        ? `same venue as ${other}`
        : `${detail} ${relativeTo.direction} ${other}`;
  }

  return (
    <span
      className={`${PILL} ${style.pill}`}
      title={
        result.gapMinutes != null
          ? `${result.gapMinutes} min between blocks · ${detail}`
          : detail
      }
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} aria-hidden />
      {style.label}
      <span className="font-mono font-normal opacity-80">· {detail}</span>
    </span>
  );
}

export function ConflictPill({ others }: { others: Block[] }) {
  const first = otherLabel(others[0]);
  const more = others.length > 1 ? ` +${others.length - 1}` : "";
  return (
    <span className={`${PILL} bg-error/10 text-error-fg`}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-error" aria-hidden />
      Overlaps {first}
      {more}
    </span>
  );
}

/** The single most useful fit signal for a block: a conflict, else the worst walk. */
export function FitPill({ fit }: { fit: FitResult | null | undefined }) {
  if (!fit) return null;
  if (fit.conflicts.length > 0) return <ConflictPill others={fit.conflicts} />;
  const worst = worstWalk(fit);
  if (!worst) return null;
  return (
    <FeasibilityBadge
      result={worst.result}
      relativeTo={{ direction: worst.direction, block: worst.other }}
    />
  );
}
