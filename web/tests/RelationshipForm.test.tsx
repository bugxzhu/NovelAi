import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RelationshipForm } from "@/components/entities/RelationshipForm";
import type { Character, Relationship } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useCharacters: () => ({ data: MOCK_CHARS }),
  useCreateRelationship: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useUpdateRelationship: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

const MOCK_CHARS: Character[] = [
  { id: 1, project_id: 1, name: "李雷", role: "protagonist",
    personality: {}, speech_style: "", background: "", motivation: "",
    appearance: "", current_state: "", affiliations: [], known_locations: [],
    created_at: "", updated_at: "" },
  { id: 2, project_id: 1, name: "韩梅", role: "supporting",
    personality: {}, speech_style: "", background: "", motivation: "",
    appearance: "", current_state: "", affiliations: [], known_locations: [],
    created_at: "", updated_at: "" },
];

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("RelationshipForm", () => {
  it("renders empty form in create mode", () => {
    renderWithProviders(<RelationshipForm projectId={1} />);
    expect(screen.getByText(/新建关系/)).toBeTruthy();
    expect(screen.getByLabelText(/From/)).toBeTruthy();
    expect(screen.getByLabelText(/To/)).toBeTruthy();
  });

  it("disables valid_from_chapter in edit mode", () => {
    const existing: Relationship = {
      id: 5, project_id: 1,
      from_char_id: 1, from_char_name: "李雷",
      to_char_id: 2, to_char_name: "韩梅",
      type: "旧友", strength: 0.5, description: "x",
      valid_from_chapter: 0, valid_to_chapter: null,
      change_summary: "", extractor_log_id: null, pending_update_id: null,
      created_at: "", updated_at: "",
    };
    renderWithProviders(<RelationshipForm projectId={1} relationship={existing} />);
    const validFromInput = screen.getByLabelText(/生效章/) as HTMLInputElement;
    expect(validFromInput.disabled).toBe(true);
  });
});
