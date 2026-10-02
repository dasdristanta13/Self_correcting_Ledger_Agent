export function validateFile(file: File, maxMb = 20): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "That file is not a PDF. Choose an invoice saved as a .pdf file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > maxMb * 1024 * 1024) return `That file is larger than ${maxMb} MB.`;
  return null;
}
