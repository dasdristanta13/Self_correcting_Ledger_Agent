import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { done } from "./fixtures";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { ApiError, getJob, listJobs, uploadInvoice } from "../api/client";

const pdf = (n: string) => new File(["%PDF-1.4"], n, { type: "application/pdf" });

beforeEach(() => {
  vi.mocked(listJobs).mockResolvedValue([]);
  vi.mocked(getJob).mockResolvedValue(done);
  vi.mocked(uploadInvoice).mockReset();
});

async function openBulk() {
  renderAt("#/upload");
  await userEvent.click(await screen.findByRole("tab", { name: "Bulk upload" }));
}

describe("BulkUpload", () => {
  it("queues PDFs, flags non-PDFs as not accepted, and never uploads those (Review Focus 6)", async () => {
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    await openBulk();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(screen.getByLabelText(/drop invoice pdfs/i), [pdf("a.pdf"), new File(["hi"], "notes.txt", { type: "text/plain" })]);
    expect(screen.getByText("2 files")).toBeInTheDocument();
    expect(screen.getByText(/not a PDF/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reconcile all" }));
    await waitFor(() => expect(screen.getByRole("link", { name: "Reconciled" })).toBeInTheDocument());
    expect(uploadInvoice).toHaveBeenCalledTimes(1);
  });

  it("runs at most three uploads at a time", async () => {
    const resolvers: (() => void)[] = [];
    vi.mocked(uploadInvoice).mockImplementation(() => new Promise((res) => { resolvers.push(() => res({ job_id: done.job_id, status: "QUEUED" })); }));
    await openBulk();
    await userEvent.upload(screen.getByLabelText(/drop invoice pdfs/i), ["1", "2", "3", "4", "5"].map((n) => pdf(`${n}.pdf`)));
    await userEvent.click(screen.getByRole("button", { name: "Reconcile all" }));
    await waitFor(() => expect(uploadInvoice).toHaveBeenCalledTimes(3));
    await act(async () => { resolvers[0](); });
    await waitFor(() => expect(uploadInvoice).toHaveBeenCalledTimes(4));
    expect(resolvers.length).toBe(4);
  });

  it("one failed upload does not stop the others and shows its message", async () => {
    vi.mocked(uploadInvoice)
      .mockRejectedValueOnce(new ApiError("too_large", "File exceeds the 20 MB limit.", 413))
      .mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    await openBulk();
    await userEvent.upload(screen.getByLabelText(/drop invoice pdfs/i), [pdf("big.pdf"), pdf("ok.pdf")]);
    await userEvent.click(screen.getByRole("button", { name: "Reconcile all" }));
    expect(await screen.findByText("File exceeds the 20 MB limit.")).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("table")).getByRole("link", { name: "Reconciled" })).toBeInTheDocument());
    expect(screen.getByText(/2 of 2 finished/)).toBeInTheDocument();
  });

  it("clears the queue", async () => {
    await openBulk();
    await userEvent.upload(screen.getByLabelText(/drop invoice pdfs/i), pdf("a.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("keeps the queue and its running uploads when switching tabs", async () => {
    let finish: () => void = () => undefined;
    vi.mocked(uploadInvoice).mockImplementation(() => new Promise((res) => { finish = () => res({ job_id: done.job_id, status: "QUEUED" }); }));
    await openBulk();
    await userEvent.upload(screen.getByLabelText(/drop invoice pdfs/i), pdf("a.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Reconcile all" }));
    await waitFor(() => expect(uploadInvoice).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole("tab", { name: "Single invoice" }));
    await userEvent.click(screen.getByRole("tab", { name: "Bulk upload" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("a.pdf")).toBeInTheDocument();
    await act(async () => { finish(); });
    await waitFor(() => expect(within(screen.getByRole("table")).getByRole("link", { name: "Reconciled" })).toBeInTheDocument());
  });
});
