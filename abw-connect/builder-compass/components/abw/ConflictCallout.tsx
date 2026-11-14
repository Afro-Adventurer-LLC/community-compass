import type { Note } from "@/services/abwApi";
import CitationChip from "./CitationChip";

export default function ConflictCallout({ notes }: { notes: Note[] }) {
  if (!notes?.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {notes.map((n, i) => {
        const conflict = n.kind === "unresolved_contradiction";
        return (
          <div
            key={i}
            className={
              conflict
                ? "rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error-fg"
                : n.kind === "alumni_experience" || n.kind === "official_over_alumni"
                  ? "rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning-fg"
                  : "rounded-lg border border-brand-blue/30 bg-brand-blue/10 px-3 py-2 text-sm text-ink"
            }
          >
            <p className="font-semibold">
              {conflict
                ? "Official sources disagree"
                : n.kind === "alumni_experience" || n.kind === "official_over_alumni"
                  ? "Alumni experience"
                  : n.kind.replace(/_/g, " ")}
            </p>
            <p className="mt-1">{n.text}</p>
            {n.citations?.length ? (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {n.citations.map((c, j) => (
                  <CitationChip key={j} citation={c} />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
