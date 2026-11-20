export const GENERATOR_MODES = ["llm", "auto", "extractive"] as const;
export type GeneratorMode = (typeof GENERATOR_MODES)[number];

/** Default shown in the selector and sent to POST /api/chat. */
export const DEFAULT_GENERATOR_MODE: GeneratorMode = "llm";

const MODE_KEY = "abw.generatorMode";
const CHOSEN_KEY = "abw.generatorMode.chosen";

export function parseGeneratorMode(raw: unknown): GeneratorMode | null {
  if (raw === "llm" || raw === "auto" || raw === "extractive") return raw;
  return null;
}

type StorageLike = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

/**
 * Restore an explicit user choice. Ignore stale extractive (or anything else)
 * that was never marked as chosen via the selector.
 */
export function loadGeneratorMode(storage?: StorageLike | null): GeneratorMode {
  if (!storage) return DEFAULT_GENERATOR_MODE;
  try {
    if (storage.getItem(CHOSEN_KEY) !== "1") return DEFAULT_GENERATOR_MODE;
    return parseGeneratorMode(storage.getItem(MODE_KEY)) ?? DEFAULT_GENERATOR_MODE;
  } catch {
    return DEFAULT_GENERATOR_MODE;
  }
}

export function saveGeneratorMode(mode: GeneratorMode, storage?: StorageLike | null): void {
  if (!storage) return;
  try {
    storage.setItem(MODE_KEY, mode);
    storage.setItem(CHOSEN_KEY, "1");
  } catch {
    /* private mode / unavailable storage */
  }
}

/** Body `mode` for POST /api/chat — the selector value, default llm. */
export function chatRequestMode(mode: GeneratorMode): GeneratorMode {
  return parseGeneratorMode(mode) ?? DEFAULT_GENERATOR_MODE;
}
