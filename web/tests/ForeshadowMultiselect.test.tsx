import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ForeshadowMultiselect } from "@/components/entities/ForeshadowMultiselect";
import type { Event } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useUpdateEvent: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

function _makeEvent(overrides: Partial<Event> = {}): Event {
  return {
    id: 1, project_id: 1, chapter_id: 10, chapter_title: "C1", chapter_order: 1,
    title: "事件A", description: "a",
    involved_characters: [], involved_character_names: [],
    location_id: null, location_name: "", plot_line_id: null,
    foreshadows: [], payoff_of: [], payoff_of_titles: [],
    is_unpaid: false,
    extractor_log_id: null, pending_update_id: null,
    created_at: "", updated_at: "",
    ...overrides,
  };
}

const MOCK_EVENTS: Event[] = [
  _makeEvent({ id: 1, title: "事件A" }),
  _makeEvent({ id: 2, title: "事件B", foreshadows: [1] }),  // B foreshadows A
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("ForeshadowMultiselect", () => {
  it("renders currently foreshadowed events as chips with remove buttons", () => {
    const target = MOCK_EVENTS[1];  // B, foreshadows=[1]
    renderWithProviders(
      <ForeshadowMultiselect event={target} allEvents={MOCK_EVENTS} />
    );
    expect(screen.getByText(/第 1 章 · 事件A/)).toBeTruthy();
    expect(screen.getAllByText(/✗/).length).toBeGreaterThan(0);
  });

  it("renders read-only payoff_of section when event has payoffs", () => {
    const targetWithPayoff = _makeEvent({
      id: 1, title: "事件A",
      foreshadows: [], payoff_of: [2], payoff_of_titles: ["事件B"],
    });
    renderWithProviders(
      <ForeshadowMultiselect event={targetWithPayoff} allEvents={MOCK_EVENTS} />
    );
    expect(screen.getByText(/此事件兑现了以下伏笔/)).toBeTruthy();
    expect(screen.getByText(/事件B/)).toBeTruthy();
  });

  it("shows empty hint when no foreshadows and no payoff_of", () => {
    const target = _makeEvent({ foreshadows: [], payoff_of: [] });
    renderWithProviders(
      <ForeshadowMultiselect event={target} allEvents={MOCK_EVENTS} />
    );
    // Both sections show "（无）"
    expect(screen.getAllByText(/（无）/).length).toBe(2);
  });
});
