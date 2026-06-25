import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { StreamView } from "@/components/generation/StreamView";
import { ToastProvider } from "@/components/ui/Toast";

vi.mock("@/lib/queries", () => ({
  useCreateChapterVersion: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock("@/components/generation/useGenerate", () => {
  const state = {
    events: [] as unknown[],
    generatedText: "",
    status: "idle" as const,
    error: null as string | null,
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
    retry: vi.fn(),
  };
  return {
    useGenerate: () => state,
    __setMockState: (s: Partial<typeof state>) => Object.assign(state, s),
    __resetMockState: () =>
      Object.assign(state, {
        events: [],
        generatedText: "",
        status: "idle" as const,
        error: null,
      }),
  };
});

function renderWithProviders(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

describe("StreamView", () => {
  beforeEach(async () => {
    const mod = await import("@/components/generation/useGenerate");
    (mod as unknown as { __resetMockState: () => void }).__resetMockState();
  });

  it("renders nothing when no events", () => {
    renderWithProviders(<StreamView chapterId={1} />);
    expect(screen.getByText(/暂无生成|准备就绪/)).toBeTruthy();
  });

  it("renders preparing hint when status is preparing and no events", async () => {
    const mod = await import("@/components/generation/useGenerate");
    (mod as unknown as { __setMockState: (s: unknown) => void }).__setMockState({
      status: "preparing",
    });
    renderWithProviders(<StreamView chapterId={1} />);
    expect(screen.getByText(/正在组装上下文/)).toBeTruthy();
  });

  it("renders meta then tokens", async () => {
    const mod = await import("@/components/generation/useGenerate");
    (mod as unknown as { __setMockState: (s: unknown) => void }).__setMockState({
      events: [
        { type: "meta", generation_log_id: 1, model: "m", model_task: "writer_long", chapter_id: 1, started_at: "s" },
        { type: "token", text: "Hello " },
        { type: "token", text: "world" },
      ],
      generatedText: "Hello world",
      status: "streaming",
    });
    renderWithProviders(<StreamView chapterId={1} />);
    expect(screen.getByText(/Hello world/)).toBeTruthy();
    expect(screen.getByText(/log_id=1/)).toBeTruthy();
  });
});
