import type { StatusKey } from "../lib/derive";

const ORDER: { key: StatusKey; label: string }[] = [
  { key: "ok", label: "Reconciled" }, { key: "wn", label: "Needs review" }, { key: "er", label: "Failed" }, { key: "in", label: "Processing" },
];

export function StatusBar({ counts }: { counts: Record<StatusKey, number> }) {
  const total = ORDER.reduce((n, o) => n + counts[o.key], 0);
  const summary = ORDER.map((o) => `${counts[o.key]} ${o.label.toLowerCase()}`).join(", ");
  return (
    <div>
      <div className="statusbar" role="img" aria-label={`Status mix: ${summary}`}>
        {ORDER.filter((o) => counts[o.key] > 0).map((o) => (
          <span key={o.key} className={`seg seg-${o.key}`} style={{ flexGrow: counts[o.key] }} />
        ))}
      </div>
      <ul className="legend">
        {ORDER.map((o) => (
          <li key={o.key}>
            <span className={`swatch seg-${o.key}`} aria-hidden="true" />{o.label}
            <span className="muted"> {counts[o.key]}{total ? ` · ${Math.round((counts[o.key] / total) * 100)}%` : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
