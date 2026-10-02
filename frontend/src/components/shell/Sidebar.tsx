import { useJobs } from "../../hooks/useJobs";
import { agentLoad, needsReview } from "../../lib/derive";
import type { Route } from "../../router";
import { ThemeToggle } from "./ThemeToggle";

const NAV: { id: string; label: string; href: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", href: "#/", icon: '<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>' },
  { id: "invoices", label: "Invoices", href: "#/invoices", icon: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h6M9 16h4"/>' },
  { id: "upload", label: "Upload", href: "#/upload", icon: '<path d="M12 16V4m0 0 4 4m-4-4-4 4"/><path d="M4 16v4h16v-4"/>' },
  { id: "review", label: "Needs review", href: "#/review", icon: '<path d="M12 4 3 20h18z"/><path d="M12 10v4"/>' },
  { id: "audit", label: "Audit trail", href: "#/audit", icon: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>' },
  { id: "settings", label: "Settings", href: "#/settings", icon: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>' },
];

export function Sidebar({ route }: { route: Route }) {
  const { jobs } = useJobs();
  const review = needsReview(jobs).length;
  const busy = agentLoad(jobs);
  const current = route.name === "detail" ? "invoices" : route.name;
  return (
    <aside className="side">
      <a className="logo" href="#/"><span className="logo-mark" aria-hidden="true">L</span>Ledger</a>
      <nav aria-label="Primary">
        <ul className="nav-list">
          {NAV.map((n) => (
            <li key={n.id}>
              <a className="nav-link" href={n.href} aria-current={current === n.id ? "page" : undefined}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{ __html: n.icon }} />
                {n.label}
                {n.id === "review" && review > 0 && <span className="nav-badge">{review}</span>}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="side-foot">
        <div className={`agent${busy > 0 ? " is-busy" : ""}`}>
          <span className="agent-dot" aria-hidden="true" />
          <div><strong>{busy > 0 ? "Agent working" : "Agent idle"}</strong>{busy > 0 ? `${busy} in progress` : "Ready for the next invoice"}</div>
        </div>
        <ThemeToggle />
      </div>
    </aside>
  );
}
