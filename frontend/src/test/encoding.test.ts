import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

const files = (dir: string): string[] =>
  readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? files(p) : [p];
  });

it("every frontend source file is strict UTF-8 without U+FFFD", () => {
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const root = join(__dirname, "..");
  for (const f of files(root)) {
    const text = decoder.decode(readFileSync(f));
    expect(text.includes("\uFFFD"), f).toBe(false);
  }
});
