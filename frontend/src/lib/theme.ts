import { useEffect, useState } from "react";
import { readJSON, writeJSON } from "./storage";

export type Theme = "system" | "light" | "dark";
const KEY = "ledger.theme";

export function applyTheme(t: Theme): void {
  const root = document.documentElement;
  if (t === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    const v = readJSON<string>(KEY, "system");
    return v === "light" || v === "dark" ? v : "system";
  });
  useEffect(() => { applyTheme(theme); }, [theme]);
  return [theme, (t) => { writeJSON(KEY, t); setTheme(t); }];
}
