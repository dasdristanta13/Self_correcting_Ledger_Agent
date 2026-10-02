import { useTheme, type Theme } from "../../lib/theme";

const OPTIONS: { id: Theme; label: string }[] = [{ id: "system", label: "System" }, { id: "light", label: "Light" }, { id: "dark", label: "Dark" }];

export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  return (
    <div className="theme" role="group" aria-label="Theme">
      {OPTIONS.map((o) => (
        <button key={o.id} type="button" aria-pressed={theme === o.id} onClick={() => setTheme(o.id)}>{o.label}</button>
      ))}
    </div>
  );
}
