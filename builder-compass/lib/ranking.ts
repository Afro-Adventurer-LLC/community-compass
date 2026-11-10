// ---------------------------------------------------------------------------
// Interest-based ranking. Pure functions, so they can move to an AWS Lambda
// later without changes.
// ---------------------------------------------------------------------------

import type { Session, UserPrefs } from "@/types";

export interface ScoreDetail {
  score: number;
  matchedTopics: string[];
  levelFit: boolean;
  roleFit: boolean;
}

const MAX_TOPIC_MATCHES = 4;

export function scoreDetail(session: Session, prefs: UserPrefs): ScoreDetail {
  const interests = new Set(prefs.interests.map((i) => i.toLowerCase()));
  const matchedTopics = session.topics.filter((t) =>
    interests.has(t.toLowerCase())
  );

  let score = Math.min(matchedTopics.length, MAX_TOPIC_MATCHES) * 3;

  // Prefer sessions near the user's depth. "No level" sessions get no bonus.
  let levelFit = false;
  if (session.level > 0) {
    const gap = Math.abs(session.level - prefs.depth) / 100;
    score += Math.max(0, 2 - gap);
    levelFit = gap <= 1;
  }

  const roleFit = session.roles.some((r) => r === prefs.role);
  if (roleFit) score += 1;

  return { score, matchedTopics, levelFit, roleFit };
}

export function scoreSession(session: Session, prefs: UserPrefs): number {
  return scoreDetail(session, prefs).score;
}

export function rankSessions(sessions: Session[], prefs: UserPrefs): Session[] {
  return [...sessions].sort((a, b) => {
    const diff = scoreSession(b, prefs) - scoreSession(a, prefs);
    return diff !== 0 ? diff : a.start.localeCompare(b.start);
  });
}

// Words that should keep their usual casing instead of "Ai" / "Ec2" / "Devops".
const SPECIAL_CASE: Record<string, string> = {
  ai: "AI",
  aws: "AWS",
  ec2: "EC2",
  ecs: "ECS",
  eks: "EKS",
  s3: "S3",
  ml: "ML",
  iot: "IoT",
  api: "API",
  sql: "SQL",
  iam: "IAM",
  vpc: "VPC",
  hpc: "HPC",
  llm: "LLM",
  saas: "SaaS",
  devops: "DevOps",
  devsecops: "DevSecOps",
  genai: "GenAI",
  mlops: "MLOps",
  finops: "FinOps",
  kiro: "Kiro",
};

export function titleCase(text: string): string {
  return text.replace(/[a-z0-9]+/gi, (word) => {
    const lower = word.toLowerCase();
    return SPECIAL_CASE[lower] ?? lower.charAt(0).toUpperCase() + lower.slice(1);
  });
}

/** Short, plain-language reasons a session was suggested. */
export function reasonsFor(session: Session, prefs: UserPrefs): string[] {
  const d = scoreDetail(session, prefs);
  const reasons: string[] = [];
  if (d.matchedTopics.length > 0) {
    reasons.push(
      `Matches ${d.matchedTopics.slice(0, 2).map(titleCase).join(" and ")}`
    );
  }
  if (session.level > 0 && d.levelFit) {
    reasons.push(`Level ${session.level} fits your depth`);
  }
  if (d.roleFit) reasons.push(`Built for ${prefs.role}`);
  return reasons;
}

/** Most common topics in the catalog, for the interests picker. */
export function topTopics(sessions: Session[], limit: number): string[] {
  const counts = new Map<string, number>();
  for (const s of sessions) {
    for (const t of s.topics) counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([t]) => t);
}

/** Roles present in the catalog, most common first. */
export function topRoles(sessions: Session[], limit: number): string[] {
  const counts = new Map<string, number>();
  for (const s of sessions) {
    for (const r of s.roles) counts.set(r, (counts.get(r) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([r]) => r);
}
