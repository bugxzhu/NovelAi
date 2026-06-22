import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscussModal } from "@/components/editor/DiscussModal";
import { useDiscussStore } from "@/lib/store";
import type { DiscussResponse } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  api: { discussChapter: vi.fn() },
  ApiError: class {},
}));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => vi.fn() }));

const mockResult: DiscussResponse = {
  question: "如果？",
  branches: [
    { label: "A", title: "直接和解", summary: "走向A", conflicts: "冲突A",
      opportunities: "机会A", character_impact: "人物A" },
    { label: "B", title: "暗中布局", summary: "走向B", conflicts: "冲突B",
      opportunities: "机会B", character_impact: "人物B" },
    { label: "C", title: "拒绝和解", summary: "走向C", conflicts: "冲突C",
      opportunities: "机会C", character_impact: "人物C" },
  ],
  recommended: "B",
  reasoning: "B 最好",
  log_id: 1,
};

describe("DiscussModal", () => {
  beforeEach(() => {
    useDiscussStore.setState({
      resultByChapter: { 5: null },
      modalOpenFor: 5,
    });
  });

  it("shows question input when no result", () => {
    render(<DiscussModal chapterId={5} />);
    expect(screen.getByPlaceholderText(/如果让李雷/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /推演/ })).toBeTruthy();
  });

  it("renders branches when result available", () => {
    useDiscussStore.setState({
      resultByChapter: { 5: mockResult },
      modalOpenFor: 5,
    });
    render(<DiscussModal chapterId={5} />);
    expect(screen.getByText(/直接和解/)).toBeTruthy();
    expect(screen.getByText(/暗中布局/)).toBeTruthy();
    expect(screen.getByText(/拒绝和解/)).toBeTruthy();
    expect(screen.getByText(/✓ 推荐/)).toBeTruthy();
  });

  it("highlights recommended branch", () => {
    useDiscussStore.setState({
      resultByChapter: { 5: mockResult },
      modalOpenFor: 5,
    });
    render(<DiscussModal chapterId={5} />);
    expect(screen.getByText(/分支 B：暗中布局/)).toBeTruthy();
  });
});
