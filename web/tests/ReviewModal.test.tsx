import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewModal } from "@/components/editor/ReviewModal";
import { useReviewStore } from "@/lib/store";
import type { Issue } from "@/lib/types";

// Mock editor — we don't test TipTap internals here
const mockEditor = {
  commands: {
    unsetAllIssueHighlights: vi.fn(),
    setIssueHighlight: vi.fn(),
    setTextSelection: vi.fn(),
    scrollIntoView: vi.fn(),
  },
  getText: vi.fn().mockReturnValue("原文 content"),
  state: { doc: { descendants: vi.fn() } },
};

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => vi.fn(),
}));

const issues: Issue[] = [
  { severity: "error", category: "character", location: "原文",
    description: "人物不一致", suggestion: "改" },
  { severity: "warn", category: "plot", location: "",
    description: "节奏过快", suggestion: "" },
];

describe("ReviewModal", () => {
  beforeEach(() => {
    useReviewStore.setState({
      issuesByChapter: { 5: issues },
      modalOpenFor: 5,
    });
  });

  it("renders by category with severity icons", () => {
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    expect(screen.getByText(/人物一致性/)).toBeTruthy();
    expect(screen.getByText(/情节矛盾/)).toBeTruthy();
    expect(screen.getByText(/人物不一致/)).toBeTruthy();
    expect(screen.getByText(/节奏过快/)).toBeTruthy();
  });

  it("shows empty state when no issues", () => {
    useReviewStore.setState({
      issuesByChapter: { 5: [] },
      modalOpenFor: 5,
    });
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    expect(screen.getByText(/未发现问题/)).toBeTruthy();
  });

  it("close button calls closeModal", async () => {
    const user = userEvent.setup();
    render(<ReviewModal chapterId={5} editor={mockEditor as any} />);
    await user.click(screen.getByRole("button", { name: /我知道了/ }));
    expect(useReviewStore.getState().modalOpenFor).toBeNull();
  });
});
