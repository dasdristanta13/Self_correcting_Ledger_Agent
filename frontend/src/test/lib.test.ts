import { describe, expect, it } from "vitest";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";
import { validateFile } from "../lib/validate";

describe("formatMoney", () => {
  it("groups thousands without touching decimals", () => {
    expect(formatMoney("1014.00")).toBe("1,014.00");
    expect(formatMoney("-5.00")).toBe("-5.00");
    expect(formatMoney("12")).toBe("12");
  });
  it("is exact beyond JS safe integers", () => {
    expect(formatMoney("123456789012345678901.50")).toBe("123,456,789,012,345,678,901.50");
  });
  it("passes through junk and shows a dash for null", () => {
    expect(formatMoney("n/a")).toBe("n/a");
    expect(formatMoney(null)).toBe("—");
  });
});

describe("labels", () => {
  it("formats provenance and field paths", () => {
    expect(provenanceLabel(1, "table_01", 1)).toBe("Page 1 · table_01 · Row 1");
    expect(provenanceLabel(2, null, null)).toBe("Page 2");
    expect(fieldLabel("items[line_01].amount")).toBe("line 01 · amount");
    expect(fieldLabel("total")).toBe("total");
  });
});

describe("validateFile", () => {
  const f = (name: string, type: string, size = 10) => new File([new Uint8Array(size)], name, { type });
  it("accepts PDFs by type or extension", () => {
    expect(validateFile(f("a.pdf", "application/pdf"))).toBeNull();
    expect(validateFile(f("a.PDF", ""))).toBeNull();
  });
  it("rejects other types, empty and oversize files", () => {
    expect(validateFile(f("a.txt", "text/plain"))).toMatch(/not a PDF/);
    expect(validateFile(f("a.pdf", "application/pdf", 0))).toMatch(/empty/);
    expect(validateFile(f("a.pdf", "application/pdf", 3 * 1024 * 1024), 2)).toMatch(/larger than 2 MB/);
  });
});
