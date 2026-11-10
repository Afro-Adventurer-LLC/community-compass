"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Check, ClipboardCheck, Copy } from "lucide-react";
import type { Session, VenueGraph } from "@/types";
import { useCompassStore } from "@/lib/store";
import { buildAiPrompt, parseAiReply, type AiPick, type AiReply } from "@/lib/planner";
import {
  fitCheck,
  plannedTitles,
  sessionToBlock,
  titleKey,
  type Block,
  type FitResult,
  type WalkLookup,
} from "@/lib/schedule";
import { copyText } from "@/lib/download";
import Button, { inputClass } from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import SessionRow from "@/components/SessionRow";

interface Checked extends AiPick {
  fit: FitResult;
}

export default function AiBridge({
  sessions,
  graph,
  days,
  blocks,
  lookup,
}: {
  sessions: Session[];
  graph: VenueGraph;
  days: string[];
  blocks: Block[];
  lookup: WalkLookup;
}) {
  const prefs = useCompassStore((s) => s.prefs);
  const addManyToPlan = useCompassStore((s) => s.addManyToPlan);

  const [copied, setCopied] = useState<"idle" | "ok" | "failed">("idle");
  const [reply, setReply] = useState("");
  const [parsed, setParsed] = useState<AiReply | null>(null);
  const [addedCount, setAddedCount] = useState<number | null>(null);

  const prompt = useMemo(
    () => buildAiPrompt({ sessions, prefs, days, graph }),
    [sessions, prefs, days, graph]
  );

  useEffect(() => {
    if (copied === "idle") return;
    const t = setTimeout(() => setCopied("idle"), 2500);
    return () => clearTimeout(t);
  }, [copied]);

  // Walk the reply in order: keep each pick that does not collide with the
  // stack or with picks accepted before it.
  const sorted = useMemo(() => {
    if (!parsed) return null;
    const have = new Set(blocks.map((b) => b.key));
    const titles = plannedTitles(blocks);
    const working: Block[] = [...blocks];
    const accepted: Checked[] = [];
    const skipped: Checked[] = [];
    const already: AiPick[] = [];
    for (const pick of parsed.picks) {
      const block = sessionToBlock(pick.session);
      // Same code, or a repeat of a session you already have.
      if (have.has(block.key) || titles.has(titleKey(pick.session.title))) {
        already.push(pick);
        continue;
      }
      titles.add(titleKey(pick.session.title));
      const fit = fitCheck(block, working, lookup);
      if (fit.conflicts.length === 0) {
        accepted.push({ ...pick, fit });
        working.push(block);
      } else {
        skipped.push({ ...pick, fit });
      }
    }
    return { accepted, skipped, already };
  }, [parsed, blocks, lookup]);

  async function copyPrompt() {
    setCopied((await copyText(prompt)) ? "ok" : "failed");
  }

  function checkReply() {
    setAddedCount(null);
    setParsed(parseAiReply(reply, sessions));
  }

  function addAccepted() {
    if (!sorted) return;
    addManyToPlan(sorted.accepted.map((a) => a.session.id));
    setAddedCount(sorted.accepted.length);
    setParsed(null);
    setReply("");
  }

  const nothingFound =
    parsed && parsed.picks.length === 0 && parsed.unknown.length === 0;

  return (
    <Card className="space-y-5">
      <div>
        <h2 className="font-semibold text-ink">Plan with your own AI</h2>
        <p className="mt-1 text-sm text-muted">
          Use any assistant you already trust. Copy the prompt, paste it into
          your AI, then paste its reply back here. Nothing is sent from this
          page.
        </p>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-ink">1. Copy this prompt</h3>
          <Button variant="secondary" onClick={copyPrompt}>
            {copied === "ok" ? (
              <ClipboardCheck size={16} strokeWidth={1.75} aria-hidden />
            ) : (
              <Copy size={16} strokeWidth={1.75} aria-hidden />
            )}
            {copied === "ok" ? "Copied" : "Copy prompt"}
          </Button>
        </div>
        <textarea
          readOnly
          rows={7}
          value={prompt}
          aria-label="Prompt for your AI"
          className={`${inputClass} font-mono text-xs leading-relaxed`}
        />
        <p className="mt-1.5 text-xs text-muted" aria-live="polite">
          {copied === "failed"
            ? "Copy did not work in this browser. Select the text above and copy it by hand."
            : "Includes your profile, the walking times, and the best-matching sessions for each day."}
        </p>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-ink">2. Paste the reply</h3>
        <textarea
          rows={5}
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          placeholder='{"picks":[{"code":"AIM302","why":"Hands-on Bedrock workshop"}]}'
          aria-label="Reply from your AI"
          className={`${inputClass} font-mono text-xs`}
        />
        <div className="mt-2">
          <Button variant="dark" onClick={checkReply} disabled={!reply.trim()}>
            Check the reply
          </Button>
        </div>
      </div>

      {addedCount !== null && (
        <p
          role="status"
          className="flex items-center gap-2 rounded-xl bg-success/10 p-3 text-sm text-success-fg"
        >
          <Check size={16} strokeWidth={2} aria-hidden />
          Added {addedCount} session{addedCount === 1 ? "" : "s"} to your stack.{" "}
          <Link href="/stack" className="font-semibold underline">
            View your stack
          </Link>
        </p>
      )}

      {nothingFound && (
        <p role="alert" className="rounded-xl bg-warning/10 p-3 text-sm text-warning-fg">
          I could not find any session codes in that reply. Ask the AI to answer
          with the JSON shape from the prompt, then paste it again.
        </p>
      )}

      {parsed && sorted && !nothingFound && (
        <div className="space-y-4">
          {sorted.accepted.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-ink">
                Ready to add ({sorted.accepted.length})
              </h3>
              <ul className="space-y-2">
                {sorted.accepted.map((a) => (
                  <SessionRow
                    key={a.session.id}
                    session={a.session}
                    fit={a.fit}
                    why={a.why}
                    showDay
                  />
                ))}
              </ul>
              <div className="mt-3">
                <Button onClick={addAccepted}>
                  Add {sorted.accepted.length} to my stack
                </Button>
              </div>
            </div>
          )}

          {sorted.skipped.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-ink">
                Skipped because they overlap ({sorted.skipped.length})
              </h3>
              <ul className="space-y-2">
                {sorted.skipped.map((a) => (
                  <SessionRow
                    key={a.session.id}
                    session={a.session}
                    fit={a.fit}
                    why={a.why}
                    showDay
                  />
                ))}
              </ul>
            </div>
          )}

          {sorted.already.length > 0 && (
            <p className="text-sm text-muted">
              Already covered by your stack (or a repeat of a session in it):{" "}
              {sorted.already.map((a) => a.session.code).join(", ")}.
            </p>
          )}

          {parsed.unknown.length > 0 && (
            <p className="text-sm text-muted">
              Not in the catalog, so ignored: {parsed.unknown.join(", ")}.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
