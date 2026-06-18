import { ApiError } from "./api";
import type { ContextBundlePreview, GenerateRequest } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";

export type GenerationEvent =
  | { type: "meta"; generation_log_id: number; model: string; model_task: string; chapter_id: number; started_at: string }
  | { type: "context"; context_bundle: ContextBundlePreview }
  | { type: "token"; text: string }
  | { type: "done"; generation_log_id: number; input_tokens: number; output_tokens: number; stop_reason: string }
  | { type: "error"; message: string; code: string };

export function parseSseChunk(chunk: string): GenerationEvent | null {
  let eventType = "";
  let dataStr = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event: ")) eventType = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataStr += line.slice(6);
  }
  if (!eventType || !dataStr) return null;
  try {
    return { type: eventType, ...JSON.parse(dataStr) } as GenerationEvent;
  } catch {
    return null;
  }
}

export async function* streamGeneration(
  chapterId: number,
  body: GenerateRequest,
  signal?: AbortSignal
): AsyncGenerator<GenerationEvent> {
  const res = await fetch(`${BASE}/api/chapters/${chapterId}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let errBody: unknown = null;
    try {
      errBody = await res.json();
    } catch {
      errBody = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, errBody);
  }

  if (!res.body) {
    yield { type: "error", message: "empty response body", code: "EmptyBody" };
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const ev = parseSseChunk(chunk);
        if (ev) yield ev;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
