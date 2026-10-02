import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";

export function NotFoundView() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState title="Nothing lives at this address" action={<a className="btn" href="#/">Back to dashboard</a>}>
        The link may be old or mistyped.
      </EmptyState>
    </>
  );
}
