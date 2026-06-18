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

  it("yields error event when server emits one", async () => {
    const chunks = [
      'event: meta\ndata: {"generation_log_id":1,"model":"m","model_task":"t","chapter_id":1,"started_at":"s"}\n\n',
      'event: error\ndata: {"message":"API down","code":"RuntimeError"}\n\n',
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events.map((e) => e.type)).toEqual(["meta", "error"]);
    const err = events[1];
    expect(err.type).toBe("error");
    if (err.type === "error") {
      expect(err.message).toBe("API down");
      expect(err.code).toBe("RuntimeError");
    }
  });

  it("yields context event with full bundle", async () => {
    const ctxBundle = {
      project: { id: 1, title: "P", genre: "g", main_theme: "t", tone: "o", premise: "p" },
      world_overview: null,
      characters: [{ id: 1, name: "Li", role: "protagonist", current_state: "ok" }],
      relationships: [],
      faction_lore: [],
      location_lore: [],
      recent_chapter_summaries: [],
    };
    const chunks = [
      `event: context\ndata: ${JSON.stringify({ context_bundle: ctxBundle })}\n\n`,
    ];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(makeReadable(chunks), { status: 200 })
    );
    const events = [];
    for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] })) {
      events.push(ev);
    }
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("context");
  });

  it("propagates AbortSignal abort as iterator rejection", async () => {
    const ac = new AbortController();
    let controller: ReadableStreamDefaultController<Uint8Array>;
    // Stream that never closes naturally — error() is called when abort fires
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
        c.enqueue(new TextEncoder().encode(
          'event: meta\ndata: {"generation_log_id":1,"model":"m","model_task":"t","chapter_id":1,"started_at":"s"}\n\n'
        ));
        // Don't close — wait for abort
      },
      cancel() {
        // Fetch calls cancel() on the body when the signal aborts
      },
    });
    // Simulate what the browser does: abort signal cancels the response body
    ac.signal.addEventListener("abort", () => controller!.error(new DOMException("The operation was aborted.", "AbortError")));

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(stream, { status: 200 })
    );

    const events: any[] = [];
    const promise = (async () => {
      for await (const ev of streamGeneration(1, { beat_text: "x", involved_character_ids: [1] }, ac.signal)) {
        events.push(ev);
        ac.abort();  // abort after first event
      }
    })();

    await expect(promise).rejects.toThrow();  // AbortError or similar
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("meta");
  });
});
