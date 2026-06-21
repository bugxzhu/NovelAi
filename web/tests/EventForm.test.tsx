import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EventForm } from "@/components/entities/EventForm";
import type { Character, Event, LoreEntry } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useCharacters: () => ({ data: MOCK_CHARS }),
  useLore: () => ({ data: MOCK_LORE }),
  useChapters: () => ({ data: MOCK_CHAPTERS }),
  usePlotLines: () => ({ data: [] }),
  useCreateEvent: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdateEvent: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

const MOCK_CHARS: Character[] = [
  { id: 1, project_id: 1, name: "李雷", role: "protagonist",
    personality: {}, speech_style: "", background: "", motivation: "",
    appearance: "", current_state: "", affiliations: [], known_locations: [],
    created_at: "", updated_at: "" },
];

const MOCK_LORE: LoreEntry[] = [
  { id: 1, project_id: 1, type: "location", name: "残月酒馆",
    title: "", description: "", attributes: {}, parent_id: null, tags: [],
    created_at: "", updated_at: "" },
];

const MOCK_CHAPTERS = [
  { id: 10, project_id: 1, order_index: 1, title: "C1", outline: "", content: "",
    status: "final", plot_line_ids: [], summary: "", content_hash: "",
    last_involved_character_ids: [], last_location_id: null,
    created_at: "", updated_at: "" },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("EventForm", () => {
  it("renders empty form in create mode", () => {
    renderWithProviders(<EventForm projectId={1} chapterId={10} />);
    expect(screen.getByText(/新建事件/)).toBeTruthy();
    expect(screen.getByLabelText(/标题/)).toBeTruthy();
    expect(screen.getByLabelText(/描述/)).toBeTruthy();
  });

  it("disables chapter select in edit mode", () => {
    const existing: Event = {
      id: 5, project_id: 1, chapter_id: 10,
      chapter_title: "C1", chapter_order: 1,
      title: "X", description: "y",
      involved_characters: [], involved_character_names: [],
      location_id: null, location_name: "", plot_line_id: null,
      foreshadows: [], payoff_of: [], payoff_of_titles: [],
      is_unpaid: false,
      extractor_log_id: null, pending_update_id: null,
      created_at: "", updated_at: "",
    };
    renderWithProviders(<EventForm projectId={1} chapterId={10} event={existing} />);
    const chapterSelect = screen.getByLabelText(/章节/) as HTMLSelectElement;
    expect(chapterSelect.disabled).toBe(true);
  });
});
