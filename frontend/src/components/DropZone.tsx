import { useId, useState, type DragEvent } from "react";
import { validateFile } from "../lib/validate";

interface Props { onFile: (file: File) => void; disabled?: boolean; maxMb?: number }

export function DropZone({ onFile, disabled = false, maxMb = 20 }: Props) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = `${inputId}-error`;

  const accept = (file: File | undefined) => {
    if (!file) return;
    const problem = validateFile(file, maxMb);
    setError(problem);
    if (!problem) onFile(file);
  };
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    if (!disabled) accept(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="dropzone-wrap">
      <input id={inputId} className="visually-hidden" type="file" accept="application/pdf,.pdf"
        disabled={disabled} aria-describedby={error ? errorId : undefined}
        onChange={(e) => { accept(e.target.files?.[0]); e.target.value = ""; }} />
      <label htmlFor={inputId}
        className={`dropzone${over ? " is-over" : ""}${disabled ? " is-disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <span className="dropzone-title">Drop an invoice PDF</span>
        <span className="dropzone-hint">
          or <span className="dropzone-link">choose a file</span>, PDF up to {maxMb} MB
        </span>
      </label>
      {error && <p id={errorId} role="alert" className="field-error">{error}</p>}
    </div>
  );
}
