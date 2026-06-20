import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CharacterStateTimeline } from "@/components/entities/CharacterStateTimeline";
import type { CharacterState } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useCharacterStates: (id: number | null) => ({
    data: id === null ? [] : MOCK_STATES,
    isLoading: false,
  }),
}));

const MOCK_STATES: CharacterState[] = [
  {
    id: 2, character_id: 1, chapter_id: 5,
    chapter_title: "残月重逢", chapter_order: 5,
    state_snapshot: "愤怒且受伤", change_summary: "被韩梅伏击",
    extractor_log_id: 10, pending_update_id: 20,
    created_at: "2026-06-20T14:30:00Z", updated_at: "2026-06-20T14:30:00Z",
  },
  {
    id: 1, character_id: 1, chapter_id: 3,
    chapter_title: "入城", chapter_order: 3,
    state_snapshot: "警惕", change_summary: "初入青石城",
    extractor_log_id: 8, pending_update_id: 18,
    created_at: "2026-06-19T10:00:00Z", updated_at: "2026-06-19T10:00:00Z",
  },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("CharacterStateTimeline", () => {
  it("renders header with count", () => {
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    expect(screen.getByText(/状态轨迹.*2/)).toBeTruthy();
  });

  it("is collapsed by default", () => {
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    // State snapshot text should not be visible until expanded
    expect(screen.queryByText("愤怒且受伤")).toBeNull();
  });

  it("expands on click and shows states", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CharacterStateTimeline characterId={1} />);
    await user.click(screen.getByRole("button", { name: /状态轨迹/ }));
    expect(screen.getByText("愤怒且受伤")).toBeTruthy();
    expect(screen.getByText("警惕")).toBeTruthy();
    expect(screen.getByText(/第 5 章 · 残月重逢/)).toBeTruthy();
    expect(screen.getByText(/被韩梅伏击/)).toBeTruthy();
  });

  it("renders empty state when no history", () => {
    renderWithProviders(<CharacterStateTimeline characterId={null} />);
    // When characterId is null, hook returns []; show placeholder
    expect(screen.getByText(/暂无状态轨迹/)).toBeTruthy();
  });
});
