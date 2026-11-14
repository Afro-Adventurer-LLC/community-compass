"use client";

import { useEffect } from "react";
import { Undo2, X } from "lucide-react";
import { hasWriting, useCompassStore } from "@/lib/store";

const VISIBLE_MS = 7000;

// Shown after anything is removed from the stack, wherever that happened.
export default function UndoToast() {
  const last = useCompassStore((s) => s.lastRemoved);
  const undo = useCompassStore((s) => s.undoRemove);
  const dismiss = useCompassStore((s) => s.dismissUndo);

  useEffect(() => {
    if (!last) return;
    const t = setTimeout(dismiss, VISIBLE_MS);
    return () => clearTimeout(t);
  }, [last, dismiss]);

  useEffect(() => {
    if (!last) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        const target = e.target as HTMLElement | null;
        // Leave native undo alone inside text fields.
        if (target?.closest("input, textarea, [contenteditable='true']")) return;
        e.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [last, undo]);

  let message = "";
  let detail = "";
  if (last?.kind === "session") {
    message = `Removed ${last.item.sessionId} from your stack`;
    if (hasWriting(last.item)) {
      detail = "Your notes are kept.";
    }
  } else if (last?.kind === "custom") {
    message = `Removed “${last.item.title}”`;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center px-4 md:pl-60"
    >
      {last && (
        <div
          key={last.at}
          className="pointer-events-auto flex max-w-md items-center gap-3 rounded-xl bg-code py-2 pl-4 pr-2 text-sm text-white shadow-[0_12px_32px_rgba(0,0,0,0.28)] ring-1 ring-white/10"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{message}</span>
            {detail && <span className="block text-xs text-white/70">{detail}</span>}
          </span>
          <button
            type="button"
            onClick={undo}
            className="inline-flex min-h-[36px] cursor-pointer items-center gap-1.5 rounded-lg px-3 font-semibold text-white transition duration-200 hover:bg-white/10"
          >
            <Undo2 size={16} strokeWidth={2} aria-hidden />
            Undo
          </button>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss"
            className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-white/70 transition duration-200 hover:bg-white/10 hover:text-white"
          >
            <X size={16} strokeWidth={2} aria-hidden />
          </button>
        </div>
      )}
    </div>
  );
}
