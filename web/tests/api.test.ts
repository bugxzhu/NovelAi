import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError } from "@/lib/api";

const BASE = "http://127.0.0.1:8005";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE", BASE);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("api", () => {
  it("GET listProjects returns parsed JSON", async () => {
    const fake = [{ id: 1, title: "P" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(fake), { status: 200 })
    );
    const out = await api.listProjects();
    expect(out).toEqual(fake);
    expect(fetch).toHaveBeenCalledWith(
      `${BASE}/api/projects`,
      expect.objectContaining({ headers: expect.objectContaining({ "Content-Type": "application/json" }) })
    );
  });

  it("POST createProject sends JSON body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 9, title: "x" }), { status: 201 })
    );
    await api.createProject({ title: "x" });
    const call = (fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ title: "x" });
  });

  it("throws ApiError on non-2xx with parsed body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "nope" }), { status: 422 })
    );
    await expect(api.getProject(99)).rejects.toMatchObject({
      status: 422,
      body: { detail: "nope" },
    });
    try {
      await api.getProject(99);
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
    }
  });

  it("handles non-JSON error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("Bad Gateway", { status: 502 })
    );
    await expect(api.getProject(1)).rejects.toMatchObject({ status: 502 });
  });

  it("updateChapter sends PATCH with partial body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 1, content: "x" }), { status: 200 })
    );
    await api.updateChapter(1, { content: "x" });
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toBe(`${BASE}/api/chapters/1`);
    expect(call[1].method).toBe("PATCH");
  });

  it("listGenerationLogs supports project_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 })
    );
    await api.listGenerationLogs({ project_id: 5 });
    expect((fetch as any).mock.calls[0][0]).toContain("project_id=5");
  });
});
