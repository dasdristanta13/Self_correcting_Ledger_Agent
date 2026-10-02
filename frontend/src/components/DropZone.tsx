import { useId, useState, type DragEvent } from "react";
import { validateFile } from "../lib/validate";

interface Props {
  onFile?: (file: File) => void;
  onFiles?: (files: File[]) => void;
  multiple?: boolean;
  title?: string;
  disabled?: boolean;
  maxMb?: number;
}

export function DropZone({ onFile, onFiles, multiple = false, title, disabled = false, maxMb = 20 }: Props) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = `${inputId}-error`;
  const heading = title ?? (multiple ? "Drop invoice PDFs" : "Drop an invoice PDF");

  const accept = (files: File[]) => {
    if (files.length === 0) return;
    if (multiple) { setError(null); onFiles?.(files); return; }   // the caller validates each file
    const problem = validateFile(files[0], maxMb);
    setError(problem);
    if (!problem) onFile?.(files[0]);
  };
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    if (!disabled) accept([...(e.dataTransfer.files ?? [])]);
  };

  return (
    <div className="dropzone-wrap">
      <input id={inputId} className="visually-hidden" type="file" accept="application/pdf,.pdf" multiple={multiple}
        disabled={disabled} aria-describedby={error ? errorId : undefined}
        onChange={(e) => { accept([...(e.target.files ?? [])]); e.target.value = ""; }} />
      <label htmlFor={inputId}
        className={`dropzone${over ? " is-over" : ""}${disabled ? " is-disabled" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
        onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <span className="dropzone-title">{heading}</span>
        <span className="dropzone-hint">
          or <span className="dropzone-link">choose {multiple ? "files" : "a file"}</span>, PDF up to {maxMb} MB{multiple ? " each" : ""}
        </span>
      </label>
      {error && <p id={errorId} role="alert" className="field-error">{error}</p>}
    </div>
  );
}
