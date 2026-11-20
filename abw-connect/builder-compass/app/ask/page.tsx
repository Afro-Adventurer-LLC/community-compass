"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { MessageCircleQuestion } from "lucide-react";
import Chat from "@/components/abw/Chat";
import PageHeader from "@/components/ui/PageHeader";

function AskInner() {
  const params = useSearchParams();
  const q = params.get("q");
  // Remount the chat when a new prefilled question arrives.
  return <Chat key={q ?? "blank"} initialQuestion={q} />;
}

export default function AskPage() {
  return (
    <div className="space-y-6">
      <div>
        <p className="mb-2 flex items-center gap-1.5 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand-purple">
          <MessageCircleQuestion size={14} strokeWidth={2} aria-hidden />
          ABW Connect
        </p>
        <PageHeader
          title="Ask ABW"
          subtitle="Source-backed answers about the All Builders Welcome grant and re:Invent, cited from official pages."
        />
      </div>
      <Suspense fallback={<div className="h-96 animate-pulse rounded-2xl bg-canvas" aria-hidden />}>
        <AskInner />
      </Suspense>
    </div>
  );
}
