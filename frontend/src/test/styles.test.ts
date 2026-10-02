import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

const dir = join(__dirname, "../styles");
const sheets = readdirSync(dir).filter((f) => f.endsWith(".css")).map((f) => [f, readFileSync(join(dir, f), "utf8")] as const);

it("has stylesheets to check", () => expect(sheets.length).toBeGreaterThan(0));

it.each(sheets)("%s contains none of the banned patterns", (_f, css) => {
  expect(css).not.toMatch(/gradient\(/);
  expect(css).not.toMatch(/backdrop-filter/);
  expect(css).not.toMatch(/border-(left|right)\s*:\s*[2-9]\d*(\.\d+)?(px|rem)/);
  expect(css).not.toMatch(/background-clip\s*:\s*text/);
});
