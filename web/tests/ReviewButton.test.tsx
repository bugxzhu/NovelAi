import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewButton } from "@/components/editor/ReviewButton";
import { useReviewStore } from "@/lib/store";

vi.mock("@/lib/api", () => ({
  api: {
    reviewChapter: vi.fn().mockResolvedValue({
      chapter_id: 5,
      issues: [
        { severity: "warn", category: "character", location: "x",
          description: "y", suggestion: "" },
      ],
      log_id: 1,
    }),
  },
  ApiError: class extends Error {
    constructor(public status: number, public body: unknown) {
      super(`HTTP ${status}`);
    }
  },
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => vi.fn(),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ReviewButton", () => {
  beforeEach(() => {
    useReviewStore.setState({ issuesByChapter: {}, modalOpenFor: null });
  });

  it("renders idle text", () => {
    renderWithProviders(<ReviewButton chapterId={5} />);
    expect(screen.getByText(/审稿/)).toBeTruthy();
  });

  it("disables during reviewing state and populates store on success", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewButton chapterId={5} />);
    const button = screen.getByRole("button", { name: /审稿/ });
    await user.click(button);
    await waitFor(() => {
      expect(useReviewStore.getState().issuesByChapter[5]).toBeDefined();
    });
    expect(useReviewStore.getState().issuesByChapter[5]).toHaveLength(1);
    expect(useReviewStore.getState().modalOpenFor).toBe(5);
  });
});
