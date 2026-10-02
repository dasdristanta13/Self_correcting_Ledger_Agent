import { useId, type KeyboardEvent } from "react";

export interface TabDef { id: string; label: string; count?: number }

export function tabIds(base: string, id: string) {
  return { tab: `${base}-tab-${id}`, panel: `${base}-panel-${id}` };
}

interface Props { tabs: TabDef[]; value: string; onChange: (id: string) => void; label: string; idBase?: string }

export function Tabs({ tabs, value, onChange, label, idBase }: Props) {
  const auto = useId();
  const base = idBase ?? auto;
  const move = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const t = tabs[(next + tabs.length) % tabs.length];
    onChange(t.id);
    document.getElementById(tabIds(base, t.id).tab)?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button key={t.id} type="button" role="tab" id={tabIds(base, t.id).tab} aria-selected={t.id === value}
          aria-controls={tabIds(base, t.id).panel} tabIndex={t.id === value ? 0 : -1}
          className={`tab${t.id === value ? " is-on" : ""}`} onClick={() => onChange(t.id)} onKeyDown={(e) => move(e, i)}>
          {t.label}{t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}
