import { describe, expect, it } from "vitest";
import { detailHref, parseHash } from "../router";

describe("parseHash", () => {
  it.each([
    ["", { name: "dashboard" }], ["#", { name: "dashboard" }], ["#/", { name: "dashboard" }],
    ["#/invoices", { name: "invoices" }], ["#/invoices/", { name: "invoices" }], ["#/upload", { name: "upload" }],
    ["#/review", { name: "review" }], ["#/audit", { name: "audit" }], ["#/settings", { name: "settings" }],
    ["#/invoices/abc", { name: "detail", id: "abc", tab: "document" }],
    ["#/invoices/abc/extracted", { name: "detail", id: "abc", tab: "extracted" }],
    ["#/invoices/abc/reconciliation", { name: "detail", id: "abc", tab: "reconciliation" }],
  ])("%j", (hash, route) => expect(parseHash(hash)).toEqual(route));

  it.each(["#/nope", "#/invoices/abc/bogus", "#/invoices/abc/document/extra", "#/upload/x", "#/invoices//document", "#/invoices//extracted"])("%s is not found", (h) =>
    expect(parseHash(h)).toEqual({ name: "notfound" }));

  it("survives a malformed percent-escape (Review Focus 3)", () => {
    expect(parseHash("#/invoices/%E0%A4%A")).toEqual({ name: "notfound" });
  });
  it("decodes ids and round-trips through detailHref", () => {
    const id = "a b/c";
    expect(detailHref(id)).toBe("#/invoices/a%20b%2Fc/document");
    expect(parseHash(detailHref(id, "extracted"))).toEqual({ name: "detail", id, tab: "extracted" });
  });
});
