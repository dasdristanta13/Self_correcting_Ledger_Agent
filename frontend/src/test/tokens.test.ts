import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "../styles/tokens.css"), "utf8");

const decls = (block: string) =>
  new Map([...block.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()] as const));

const light = decls(css.match(/:root\s*\{([^}]*)\}/)![1]);
const darkMedia = decls(
  css.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme="light"\]\)\s*\{([^}]*)\}/)![1],
);
const darkForced = decls(css.match(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/)![1]);

function oklchToLuminance(v: string): number {
  const m = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(v);
  if (!m) throw new Error(`not a plain oklch(): ${v}`);
  const [L, C, h] = [Number(m[1]), Number(m[2]), (Number(m[3]) * Math.PI) / 180];
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const mm = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  const r = clamp(4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s);
  const g = clamp(-1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s);
  const bl = clamp(-0.0041960863 * l - 0.7034186147 * mm + 1.707614701 * s);
  return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
}
const contrast = (fg: string, bg: string) => {
  const [a, b] = [oklchToLuminance(fg), oklchToLuminance(bg)];
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
};

const PAIRS: [string, string][] = [
  ["--ink", "--bg"], ["--ink", "--surface"], ["--muted", "--bg"], ["--muted", "--surface"], ["--muted", "--sunk"],
  ["--accent", "--surface"], ["--accent", "--accent-wash"], ["--on-accent", "--accent-solid"],
  ["--good", "--good-bg"], ["--warn", "--warn-bg"], ["--bad", "--bad-bg"],
  ["--good", "--surface"], ["--warn", "--surface"], ["--bad", "--surface"],
];

describe.each([["light", light], ["dark (OS preference)", darkMedia]])("%s theme", (_name, t) => {
  it.each(PAIRS)("%s on %s is at least 4.5:1", (fg, bg) => {
    expect(contrast(t.get(fg)!, t.get(bg)!)).toBeGreaterThanOrEqual(4.5);
  });
});

it("non-text line-strong is at least 3:1 against surface in both themes", () => {
  expect(contrast(light.get("--line-strong")!, light.get("--surface")!)).toBeGreaterThanOrEqual(3);
  expect(contrast(darkMedia.get("--line-strong")!, darkMedia.get("--surface")!)).toBeGreaterThanOrEqual(3);
});

it("the forced-dark block is identical to the OS-dark block", () => {
  expect([...darkForced]).toEqual([...darkMedia]);
});
