import type { Note } from "@/services/api";
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
                ? "rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-950"
                : n.kind === "alumni_experience" || n.kind === "official_over_alumni"
                  ? "rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
                  : "rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950"
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
