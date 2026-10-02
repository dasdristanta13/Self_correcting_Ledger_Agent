import { useMemo, useSyncExternalStore } from "react";

export type DetailTab = "document" | "extracted" | "reconciliation";
export type Route =
  | { name: "dashboard" | "invoices" | "upload" | "review" | "audit" | "settings" | "notfound" }
  | { name: "detail"; id: string; tab: DetailTab };

const TABS: DetailTab[] = ["document", "extracted", "reconciliation"];
const TOP = ["invoices", "upload", "review", "audit", "settings"] as const;
const NOT_FOUND: Route = { name: "notfound" };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "").replace(/\/+$/, "");
  if (path === "") return { name: "dashboard" };
  const [head, rawId, rawTab, ...rest] = path.split("/");
  if (rest.length > 0) return NOT_FOUND;
  if (head === "invoices" && rawId !== undefined) {
    let id: string;
    try { id = decodeURIComponent(rawId); } catch { return NOT_FOUND; }
    if (rawTab === undefined) return { name: "detail", id, tab: "document" };
    return (TABS as string[]).includes(rawTab) ? { name: "detail", id, tab: rawTab as DetailTab } : NOT_FOUND;
  }
  if (rawId !== undefined) return NOT_FOUND;
  return (TOP as readonly string[]).includes(head) ? ({ name: head } as Route) : NOT_FOUND;
}

export const detailHref = (id: string, tab: DetailTab = "document") => `#/invoices/${encodeURIComponent(id)}/${tab}`;

export function navigate(href: string): void {
  window.location.hash = href.replace(/^#/, "");
}

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash, () => "");
  return useMemo(() => parseHash(hash), [hash]);
}
