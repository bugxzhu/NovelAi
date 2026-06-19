import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StreamView } from "@/components/generation/StreamView";

vi.mock("@/components/generation/useGenerate", () => {
  const state = {
    events: [],
    generatedText: "",
    status: "idle" as const,
    error: null,
    start: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
  };
  return {
    useGenerate: () => state,
    __setMockState: (s: Partial<typeof state>) => Object.assign(state, s),
  };
});

describe("StreamView", () => {
  it("renders nothing when no events", () => {
    render(<StreamView chapterId={1} />);
    expect(screen.getByText(/暂无生成|准备就绪/)).toBeTruthy();
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
    render(<StreamView chapterId={1} />);
    expect(screen.getByText(/Hello world/)).toBeTruthy();
    expect(screen.getByText(/log_id=1/)).toBeTruthy();
  });
});
