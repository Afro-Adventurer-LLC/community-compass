import type { Citation } from "@/services/api";

export default function CitationChip({ citation }: { citation: Citation }) {
  const alumni = citation.source_type === "alumni_experience" || citation.alumni_experience;
  const label = [citation.title, citation.section].filter(Boolean).join(" · ");
  const inner = (
    <>
      <span className="truncate max-w-[14rem] sm:max-w-[18rem]">{label || "Source"}</span>
      {alumni ? (
        <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
          Personal experience
        </span>
      ) : (
        <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-700">
          Official
        </span>
      )}
    </>
  );
  const cls =
    "inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-ink-700 hover:border-accent";
  if (citation.source_url) {
    return (
      <a className={cls} href={citation.source_url} target="_blank" rel="noreferrer">
        {inner}
      </a>
    );
  }
  return <span className={cls}>{inner}</span>;
}
