// ---------------------------------------------------------------------------
// Export the schedule / trip report as Markdown.
// ---------------------------------------------------------------------------

import type { PlanItem, Session } from "@/types";
import { dateOf, dayLong, rangeLabel } from "@/lib/format";
import type { Block } from "@/lib/schedule";

export function scheduleToMarkdown(blocks: Block[], plan: PlanItem[]): string {
  const lines: string[] = [
    "# My re:Invent 2026 schedule",
    "",
    "_Built with Builder Compass. All times are Las Vegas time (PT)._",
  ];

  if (blocks.length === 0) {
    lines.push("", "_No sessions planned yet._");
    return lines.join("\n");
  }

  const noteById = new Map(plan.map((p) => [p.sessionId, p.note?.text]));

  let currentDay = "";
  for (const b of blocks) {
    const day = dateOf(b.start);
    if (day !== currentDay) {
      currentDay = day;
      lines.push("", `## ${dayLong(day)}`, "");
    }

    const when = rangeLabel(b.start, b.end);
    const where = [b.venue, b.room].filter(Boolean).join(" · ");

    if (b.kind === "session" && b.session) {
      const s = b.session;
      const meta = [s.track, s.level ? `Level ${s.level}` : null, s.type]
        .filter(Boolean)
        .join(" · ");
      lines.push(`- **${when}** · ${s.code}: ${s.title}`, `  - ${meta}`);
      if (where) {
        lines.push(
          `  - ${where}${s.reservable ? "" : " · walk-up"}${b.status ? ` · ${b.status}` : ""}`
        );
      }
      const note = noteById.get(s.id);
      if (note) lines.push(`  - Note: ${note.replace(/\n+/g, " ")}`);
    } else {
      lines.push(`- **${when}** · ${b.title} _(custom)_`);
      if (where) lines.push(`  - ${where}`);
    }
  }

  return lines.join("\n");
}

export function reportToMarkdown(plan: PlanItem[], sessions: Session[]): string {
  const byId = new Map(sessions.map((s) => [s.id, s]));
  const lines: string[] = ["# re:Invent 2026 trip report", ""];

  const entries = plan.filter(
    (p) =>
      (p.rating &&
        (p.rating.value > 0 ||
          p.rating.takeaway ||
          p.rating.actionItems ||
          p.rating.wouldRecommend !== undefined)) ||
      p.note?.text
  );

  if (entries.length === 0) {
    lines.push("_No notes or ratings captured yet._");
    return lines.join("\n");
  }

  // Actions first, for whoever approved the trip.
  lines.push("## Action items", "");
  let anyAction = false;
  for (const p of entries) {
    const s = byId.get(p.sessionId);
    const action = p.rating?.actionItems?.trim();
    if (s && action) {
      anyAction = true;
      lines.push(`- (${s.code}) ${action.replace(/\n+/g, " ")}`);
    }
  }
  if (!anyAction) lines.push("_None recorded._");

  lines.push("", "## Sessions", "");
  for (const p of entries) {
    const s = byId.get(p.sessionId);
    if (!s) continue;
    lines.push(`### ${s.code}: ${s.title}`);
    const r = p.rating;
    if (r && r.value > 0) lines.push(`- Rating: ${r.value}/5`);
    if (r && r.wouldRecommend !== undefined) {
      lines.push(`- ${r.wouldRecommend ? "Would recommend" : "Would not recommend"}`);
    }
    if (r?.takeaway?.trim()) lines.push(`- Takeaway: ${r.takeaway.trim()}`);
    if (p.note?.text) lines.push(`- Notes: ${p.note.text.replace(/\n+/g, " ")}`);
    lines.push("");
  }

  return lines.join("\n");
}
