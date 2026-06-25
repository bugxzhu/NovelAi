import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import VersionsPage from "@/app/projects/[projectId]/chapters/[chapterId]/versions/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ projectId: "1", chapterId: "10" }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/queries", () => ({
  useChapterVersions: () => ({
    data: [
      { id: 1, chapter_id: 10, char_count: 100, delta_char_count: -50, reason: "manual", created_at: "2026-06-25T10:00:00Z" },
      { id: 2, chapter_id: 10, char_count: 150, delta_char_count: 0, reason: "pre_ai_accept", created_at: "2026-06-25T09:00:00Z" },
    ],
    isLoading: false,
  }),
  useChapterVersion: (id: number) => ({
    data: id === 1
      ? { id: 1, chapter_id: 10, char_count: 100, reason: "manual", created_at: "2026-06-25T10:00:00Z", content: "version one content" }
      : id === 2
        ? { id: 2, chapter_id: 10, char_count: 150, reason: "pre_ai_accept", created_at: "2026-06-25T09:00:00Z", content: "version two content" }
        : null,
    isLoading: false,
  }),
  useRestoreChapterVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => vi.fn(),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ChapterVersionsPage", () => {
  it("renders version list in correct order", () => {
    renderWithProviders(<VersionsPage />);
    // selectedId auto-selects versions[0]=manual on mount, so "手动" appears
    // in both the list item AND the preview header — use getAllByText.
    expect(screen.getAllByText("手动").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("AI 生成前")).toBeInTheDocument();
  });

  it("clicking a list item loads its content into preview", async () => {
    renderWithProviders(<VersionsPage />);
    // selectedId defaults to null on mount, useEffect auto-selects versions[0].id=1
    await waitFor(() => {
      expect(screen.getByText("version one content")).toBeInTheDocument();
    });
    // Click second item (AI 生成前 → id 2)
    fireEvent.click(screen.getByText("AI 生成前"));
    await waitFor(() => {
      expect(screen.getByText("version two content")).toBeInTheDocument();
    });
  });

  it("restore button is visible when a version is selected", async () => {
    renderWithProviders(<VersionsPage />);
    await waitFor(() => {
      expect(screen.getByText("version one content")).toBeInTheDocument();
    });
    expect(screen.getByText("⏩ 恢复此版本")).toBeInTheDocument();
  });
});
