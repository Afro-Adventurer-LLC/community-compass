import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import {
  DEFAULT_GENERATOR_MODE,
  chatRequestMode,
  loadGeneratorMode,
  parseGeneratorMode,
  saveGeneratorMode,
} from "./generatorMode.ts";

function memoryStore(init: Record<string, string> = {}) {
  const data = { ...init };
  return {
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
    data,
  };
}

describe("generator default", () => {
  it("defaults to llm, not extractive", () => {
    assert.equal(DEFAULT_GENERATOR_MODE, "llm");
    assert.equal(loadGeneratorMode(null), "llm");
    assert.equal(loadGeneratorMode(memoryStore()), "llm");
    assert.equal(chatRequestMode("llm"), "llm");
  });

  it("ignores stale extractive that the user did not choose", () => {
    const store = memoryStore({ "abw.generatorMode": "extractive" });
    assert.equal(loadGeneratorMode(store), "llm");
  });

  it("keeps extractive after an explicit selector change", () => {
    const store = memoryStore();
    saveGeneratorMode("extractive", store);
    assert.equal(loadGeneratorMode(store), "extractive");
    assert.equal(chatRequestMode("extractive"), "extractive");
  });

  it("rejects unknown stored values", () => {
    assert.equal(parseGeneratorMode("bedrock"), null);
    const store = memoryStore({ "abw.generatorMode": "nope", "abw.generatorMode.chosen": "1" });
    assert.equal(loadGeneratorMode(store), "llm");
  });

  it("Chat selector defaults to llm and posts mode llm", () => {
    const src = readFileSync(new URL("../components/Chat.tsx", import.meta.url), "utf8");
    assert.match(src, /useState<GeneratorMode>\(["']llm["']\)/);
    assert.match(src, /mode: chatRequestMode\(mode\)/);
    assert.doesNotMatch(src, /useState(?:<GeneratorMode>)?\(["']extractive["']\)/);
  });
});
