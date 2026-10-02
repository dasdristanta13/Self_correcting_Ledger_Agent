import { useEffect, useRef, type ReactNode } from "react";
import { Sidebar } from "./components/shell/Sidebar";
import { JobsProvider } from "./hooks/useJobs";
import { useRoute, type Route } from "./router";
import { DashboardView } from "./views/DashboardView";
import { InvoicesView } from "./views/InvoicesView";
import { AuditView } from "./views/AuditView";
import { NotFoundView } from "./views/NotFoundView";
import { UploadView } from "./views/UploadView";
import { ReviewView } from "./views/ReviewView";

function viewFor(route: Route): ReactNode {
  switch (route.name) {
    case "dashboard": return <DashboardView />;
    case "invoices": return <InvoicesView />;
    case "upload": return <UploadView />;
    case "review": return <ReviewView />;
    case "audit": return <AuditView />;
    default: return <NotFoundView />;     // later tasks register their views here
  }
}

function Shell() {
  const route = useRoute();
  const mainRef = useRef<HTMLElement>(null);
  const first = useRef(true);
  const routeKey = route.name === "detail" ? `detail:${route.id}` : route.name;

  useEffect(() => {
    if (first.current) { first.current = false; return; }
    const h1 = mainRef.current?.querySelector("h1");
    if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
    window.scrollTo(0, 0);
  }, [routeKey]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); mainRef.current?.focus(); }}>Skip to content</a>
      <Sidebar route={route} />
      <main id="main" className="main" ref={mainRef} tabIndex={-1}>
        <div className="view">{viewFor(route)}</div>
      </main>
    </div>
  );
}

export default function App() {
  return <JobsProvider><Shell /></JobsProvider>;
}
