import type { Citation } from "@/services/abwApi";

export default function CitationChip({ citation }: { citation: Citation }) {
  const alumni = citation.source_type === "alumni_experience" || citation.alumni_experience;
  const label = [citation.title, citation.section].filter(Boolean).join(" · ");
  const inner = (
    <>
      <span className="truncate max-w-[14rem] sm:max-w-[18rem]">{label || "Source"}</span>
      {alumni ? (
        <span className="rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning-fg">
          Personal experience
        </span>
      ) : (
        <span className="rounded-full bg-brand-tint px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-purple">
          Official
        </span>
      )}
    </>
  );
  const cls =
    "inline-flex items-center gap-1.5 rounded-full border border-border bg-canvas px-2.5 py-1 text-xs text-ink hover:border-brand-purple";
  if (citation.source_url) {
    return (
      <a className={cls} href={citation.source_url} target="_blank" rel="noreferrer">
        {inner}
      </a>
    );
  }
  return <span className={cls}>{inner}</span>;
}
