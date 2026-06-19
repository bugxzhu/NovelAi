import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GenerateForm } from "@/components/generation/GenerateForm";

// Stub the useGenerate hook
vi.mock("@/components/generation/useGenerate", () => ({
  useGenerate: () => ({
    events: [],
    generatedText: "",
    status: "idle",
    error: null,
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    retry: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "1", chapterId: "1" }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
  );
}

describe("GenerateForm", () => {
  it("disables submit when beat is empty", () => {
    renderWithProviders(<GenerateForm chapterId={1} />);
    const btn = screen.getByRole("button", { name: /生成/ });
    expect(btn).toBeDisabled();
  });

  it("disables submit when no character selected", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GenerateForm chapterId={1} />);
    await user.type(screen.getByPlaceholderText(/李雷推开/), "主角遇旧友");
    expect(screen.getByRole("button", { name: /生成/ })).toBeDisabled();
  });
});
