import { describe, it, expect, vi, afterEach } from "vitest";
import { streamGeneration, parseSseChunk } from "@/lib/sse";
import { ApiError } from "@/lib/api";

function makeReadable(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("parseSseChunk", () => {
  it("parses single token event", () => {
    const chunk = "event: token\ndata: {\"text\":\"hi\"}\n";
    const ev = parseSseChunk(chunk);
    expect(ev).toEqual({ type: "token", text: "hi" });
  });

  it("parses meta event", () => {
    const chunk = 'event: meta\ndata: {"generation_log_id":1,"model":"x","model_task":"y","chapter_id":2,"started_at":"z"}\n';
    const ev = parseSseChunk(chunk);
    expect(ev?.type).toBe("meta");
    expect(ev && "generation_log_id" in ev && ev.generation_log_id).toBe(1);
  });

  it("parses event with Chinese content", () => {
    const chunk = 'event: token\ndata: {"text":"你好"}\n';
    const ev = parseSseChunk(chunk);
    expect(ev).toEqual({ type: "token", text: "你好" });
  });

  it("returns null on incomplete chunk", () => {
    expect(parseSseChunk("data: foo\n")).toBeNull();
  });
});

describe("streamGeneration", () => {
  it("yields events across multiple byte chunks", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    const chunks = [
      "event: meta\ndata: {\"generation_log_id\":1,\"model\":\"m\",\"model_task\":\"t\",\"chapter_id\":1,\"started_at\":\"s\"}\n\n",
      "event: token\ndata: {\"text\":\"Hello \"}\n\nevent: token\ndata: {\"text\":\"world\"}\n\n",
      "event: done\ndata: {\"generation_log_id\":1,\"input_tokens\":10,\"output_tokens\":2,\"stop_reason\":\"end_turn\"}\n\n",
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events.map((e) => e.type)).toEqual(["meta", "token", "token", "done"]);
  });

  it("buffers partial events across chunks", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    const chunks = [
      "event: token\ndata: {\"text\":",  // partial
      "\"half\"}\n\n",
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ type: "token", text: "half" });
  });

  it("throws ApiError on non-2xx", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE", "http://x");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "bad" }), { status: 422 })
    );
    await expect(
      (async () => {
        for await (const _ of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
          // drain
        }
      })()
    ).rejects.toBeInstanceOf(ApiError);
  });
});
