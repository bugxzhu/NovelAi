import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PendingUpdateItem } from "@/components/entities/PendingUpdateItem";
import type { PendingUpdateRead } from "@/lib/types";

vi.mock("@/lib/queries", () => ({
  useAcceptPendingUpdate: () => ({ mutate: vi.fn(), isPending: false }),
  useRejectPendingUpdate: () => ({ mutate: vi.fn(), isPending: false }),
}));

function renderWithProviders(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const basePending: PendingUpdateRead = {
  id: 1, project_id: 1, chapter_id: 1,
  update_type: "hard_fact",
  operation: "create",
  target_table: "characters",
  target_id: null,
  reason: "第 3 段首次出现",
  status: "pending",
  entity_name: "韩梅",
  entity_type: "",
  field_name: "",
  old_value: "",
  proposed_value: "酒馆老板娘",
  created_at: "2026-06-19T10:00:00Z",
  updated_at: "2026-06-19T10:00:00Z",
};

describe("PendingUpdateItem", () => {
  it("renders create character", () => {
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    expect(screen.getByText(/新建人物/)).toBeInTheDocument();
    expect(screen.getByText(/新建人物.*韩梅/)).toBeInTheDocument();
    expect(screen.getByText("酒馆老板娘")).toBeInTheDocument();
    expect(screen.getByText(/第 3 段首次出现/)).toBeInTheDocument();
  });

  it("renders update character with old/new", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{
        ...basePending,
        operation: "update",
        field_name: "background",
        old_value: "南方孤儿",
        proposed_value: "南方孤儿，曾在守夜人服役",
      }} />
    );
    expect(screen.getByText(/更新人物/)).toBeInTheDocument();
    expect(screen.getByText(/南方孤儿$/)).toBeInTheDocument();
    expect(screen.getByText(/南方孤儿，曾在守夜人服役/)).toBeInTheDocument();
  });

  it("renders create lore with type", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{
        ...basePending,
        target_table: "lore_entries",
        entity_name: "残月酒馆",
        entity_type: "location",
        proposed_value: "青石城南门",
      }} />
    );
    expect(screen.getByText(/新建设定/)).toBeInTheDocument();
    expect(screen.getByText("[地点]")).toBeInTheDocument();
  });

  it("calls accept mutation on click", async () => {
    const user = userEvent.setup();
    const fn = vi.fn();
    const mod = await import("@/lib/queries");
    vi.spyOn(mod, "useAcceptPendingUpdate").mockReturnValue({
      mutate: fn, isPending: false,
    } as any);
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    await user.click(screen.getByRole("button", { name: /接受/ }));
    expect(fn).toHaveBeenCalledWith(basePending.id);
  });

  it("calls reject mutation on click", async () => {
    const user = userEvent.setup();
    const fn = vi.fn();
    // Mock window.prompt to skip the note input
    vi.spyOn(window, "prompt").mockReturnValue("");
    const mod = await import("@/lib/queries");
    vi.spyOn(mod, "useRejectPendingUpdate").mockReturnValue({
      mutate: fn, isPending: false,
    } as any);
    renderWithProviders(<PendingUpdateItem pending={basePending} />);
    await user.click(screen.getByRole("button", { name: /拒绝/ }));
    expect(fn).toHaveBeenCalledWith({ id: basePending.id, note: "" });
  });

  it("shows status badge for already decided", () => {
    renderWithProviders(
      <PendingUpdateItem pending={{ ...basePending, status: "accepted" }} />
    );
    expect(screen.queryByRole("button", { name: /接受/ })).not.toBeInTheDocument();
    expect(screen.getByText(/已接受/)).toBeInTheDocument();
  });
});

describe("PendingUpdateItem — character_states", () => {
  const statePending: PendingUpdateRead = {
    ...basePending,
    id: 2,
    update_type: "soft_fact",
    target_table: "character_states",
    entity_name: "李雷",
    field_name: "state_snapshot",
    proposed_value: "愤怒且受伤；决心复仇",
    reason: "chapter_id=5 状态变化",
  };

  it("renders state change card with 📝 icon and snapshot", () => {
    renderWithProviders(<PendingUpdateItem pending={statePending} />);
    expect(screen.getByText(/📝/)).toBeTruthy();
    expect(screen.getByText(/状态变化 · 李雷/)).toBeTruthy();
    expect(screen.getByText(/李雷/)).toBeTruthy();
    expect(screen.getByText(/愤怒且受伤；决心复仇/)).toBeTruthy();
  });

  it("does not render 旧值/新值 diff for state changes", () => {
    renderWithProviders(<PendingUpdateItem pending={statePending} />);
    // state_snapshot already shown via proposed_value; should NOT also show
    // "新值：" prefix (which is for update ops with field_name)
    expect(screen.queryByText(/新值：/)).toBeNull();
  });
});

describe("PendingUpdateItem — relationships", () => {
  const relPending: PendingUpdateRead = {
    ...basePending,
    id: 3,
    update_type: "soft_fact",
    target_table: "relationships",
    entity_name: "李雷 → 韩梅",
    field_name: "",
    proposed_value: "仇人（强度 -0.8）：决心复仇",
    reason: "",
  };

  it("renders relationship card with 🤝 icon and direction", () => {
    renderWithProviders(<PendingUpdateItem pending={relPending} />);
    expect(screen.getByText(/🤝/)).toBeTruthy();
    expect(screen.getByText(/关系变化/)).toBeTruthy();
    expect(screen.getByText(/李雷 → 韩梅/)).toBeTruthy();
    expect(screen.getByText(/仇人（强度 -0.8）/)).toBeTruthy();
  });

  it("does not render 旧值/新值 diff for relationships", () => {
    renderWithProviders(<PendingUpdateItem pending={relPending} />);
    expect(screen.queryByText(/新值：/)).toBeNull();
    expect(screen.queryByText(/旧值：/)).toBeNull();
  });
});
