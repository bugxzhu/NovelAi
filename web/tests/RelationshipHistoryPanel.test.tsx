import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RelationshipHistoryPanel } from "@/components/entities/RelationshipHistoryPanel";
import type { RelationshipHistoryItem } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useRelationshipHistory: (fromId: number | null, toId: number | null) => ({
    data: fromId === null || toId === null ? [] : MOCK,
    isLoading: false,
  }),
}));

const MOCK: RelationshipHistoryItem[] = [
  {
    version_id: 2, valid_from_chapter: 5, valid_to_chapter: null,
    type: "仇人", strength: -0.8, description: "决心复仇",
    change_summary: "伏击", created_at: "2026-06-20T14:00:00Z",
  },
  {
    version_id: 1, valid_from_chapter: 0, valid_to_chapter: 5,
    type: "旧友", strength: 0.5, description: "童年同伴",
    change_summary: "开章前", created_at: "2026-06-19T10:00:00Z",
  },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("RelationshipHistoryPanel", () => {
  it("renders header with version count", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    expect(screen.getByText(/演变历史.*2/)).toBeTruthy();
  });

  it("is expanded by default (not collapsed)", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    // Versions should be visible without clicking
    expect(screen.getByText("仇人")).toBeTruthy();
    expect(screen.getByText("旧友")).toBeTruthy();
  });

  it("renders chapter range and version metadata", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={1} toId={2} />);
    expect(screen.getByText(/第 5 章 → 当前/)).toBeTruthy();
    expect(screen.getByText(/第 0 章 → 第 5 章/)).toBeTruthy();
    expect(screen.getByText(/伏击/)).toBeTruthy();
  });

  it("renders empty state when no history", () => {
    renderWithProviders(<RelationshipHistoryPanel fromId={null} toId={null} />);
    expect(screen.getByText(/暂无演变历史/)).toBeTruthy();
  });
});
