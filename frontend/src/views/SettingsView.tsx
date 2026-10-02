import { useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { Switch } from "../components/ui/Switch";
import { Tabs, tabIds } from "../components/ui/Tabs";
import { defaultSettings, loadSettings, saveSettings, SETTING_GROUPS, type SettingValue } from "../lib/settings";

const FAIL = "Couldn't save in this browser. Your changes apply to this session only.";

export function SettingsView() {
  const [saved, setSaved] = useState(loadSettings);
  const [draft, setDraft] = useState(saved);
  const [group, setGroup] = useState("General");
  const [note, setNote] = useState<string | null>(null);
  const dirty = Object.keys(draft).some((k) => draft[k] !== saved[k]);
  const set = (key: string, v: SettingValue) => { setDraft((d) => ({ ...d, [key]: v })); setNote(null); };

  return (
    <>
      <PageHeader title="Settings" sub="Configure extraction, validation and agent behaviour."
        actions={<>
          <button type="button" className="btn" onClick={() => { setDraft(defaultSettings()); setNote(null); }}>Reset to defaults</button>
          <button type="button" className="btn btn-primary" disabled={!dirty} onClick={() => { if (saveSettings(draft)) { setSaved(draft); setNote("Saved in this browser"); } else setNote(FAIL); }}>Save changes</button>
        </>} />
      <p className="banner">Preview: these preferences are stored in this browser and are not yet applied by the agent. Server-side defaults live in <code>configs/default.yaml</code>.</p>
      <Tabs label="Settings sections" value={group} onChange={setGroup} idBase="set" tabs={Object.keys(SETTING_GROUPS).map((g) => ({ id: g, label: g }))} />
      <section className="panel settings-panel" role="tabpanel" id={tabIds("set", group).panel} aria-labelledby={tabIds("set", group).tab}>
        {SETTING_GROUPS[group].map((d) => (
          <div className="set" key={d.key}>
            <div><span className="set-label">{d.label}</span>{d.hint && <span className="muted set-hint">{d.hint}</span>}</div>
            {d.kind === "toggle"
              ? <Switch checked={draft[d.key] as boolean} label={d.label} onChange={(v) => set(d.key, v)} />
              : <select aria-label={d.label} value={draft[d.key] as string} onChange={(e) => set(d.key, e.target.value)}>
                  {d.options!.map((o) => <option key={o}>{o}</option>)}
                </select>}
          </div>
        ))}
      </section>
      {note && <p role={note === FAIL ? "alert" : "status"} className="muted note">{note}</p>}
    </>
  );
}
