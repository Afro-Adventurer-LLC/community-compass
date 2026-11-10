import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { findSession, loadSessions, relatedSessions } from "@/lib/data.server";
import { dayLong, rangeLabel } from "@/lib/format";
import SessionDetail from "@/components/SessionDetail";

// Every session page is rendered at build time; unknown codes are a 404.
export const dynamicParams = false;

export function generateStaticParams() {
  return loadSessions().map((s) => ({ id: s.id }));
}

function lookup(rawId: string) {
  let id = rawId;
  try {
    id = decodeURIComponent(rawId);
  } catch {
    /* keep the raw value */
  }
  return findSession(id);
}

export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const session = lookup(params.id);
  if (!session) return { title: "Session not found — Builder Compass" };
  const when = `${dayLong(session.start)}, ${rangeLabel(session.start, session.end)}`;
  const description = `${session.type} · ${session.venue} · ${when}. ${session.abstract}`.slice(0, 200);
  return {
    title: `${session.code}: ${session.title} — Builder Compass`,
    description,
    openGraph: { title: `${session.code}: ${session.title}`, description },
  };
}

export default function SessionPage({ params }: { params: { id: string } }) {
  const session = lookup(params.id);
  if (!session) notFound();
  return <SessionDetail session={session} related={relatedSessions(session)} />;
}
