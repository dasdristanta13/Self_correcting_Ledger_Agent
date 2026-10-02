import { useState, type ReactNode } from "react";

export function Disclosure({ title, children, onOpen }: { title: string; children: ReactNode; onOpen?: () => void }) {
  const [opened, setOpened] = useState(false);
  return (
    <details className="disclosure" onToggle={(e) => {
      const open = (e.currentTarget as HTMLDetailsElement).open;
      if (open && !opened) { setOpened(true); onOpen?.(); }
    }}>
      <summary>{title}</summary>
      {opened && <div className="disclosure-body">{children}</div>}
    </details>
  );
}
