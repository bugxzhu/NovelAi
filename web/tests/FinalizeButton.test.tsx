import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FinalizeButton } from "@/components/editor/FinalizeButton";
import { ToastProvider } from "@/components/ui/Toast";

vi.mock("@/lib/queries", () => ({
  useCreateChapterVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>
  );
}

describe("FinalizeButton", () => {
  it("shows default text when not final", () => {
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    expect(screen.getByRole("button", { name: /完成本章/ })).toBeInTheDocument();
  });

  it("shows refinalize text when already final", () => {
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={true} />);
    expect(screen.getByRole("button", { name: /重新抽取/ })).toBeInTheDocument();
  });

  it("disables and shows spinner during finalizing", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => {}) // never resolves
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    const btn = screen.getByRole("button", { name: /完成本章/ });
    await user.click(btn);
    expect(screen.getByRole("button", { name: /抽取中/ })).toBeDisabled();
  });

  it("shows success toast with pending count on 200", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        chapter_id: 1, summary: "x", pending_created: 3, log_id: 1,
      }), { status: 200 })
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    await user.click(screen.getByRole("button", { name: /完成本章/ }));
    await waitFor(() => {
      expect(screen.getByText(/已抽取 3 条新事实/)).toBeInTheDocument();
    });
  });

  it("shows error toast on 422", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        detail: { error: "extraction_failed", reason: "bad json", raw: "..." }
      }), { status: 422 })
    );
    renderWithProviders(<FinalizeButton chapterId={1} isFinal={false} />);
    await user.click(screen.getByRole("button", { name: /完成本章/ }));
    await waitFor(() => {
      expect(screen.getByText(/抽取失败/)).toBeInTheDocument();
    });
  });
});
