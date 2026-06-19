"use client";

import { useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamGeneration, type GenerationEvent } from "@/lib/sse";
import { ApiError } from "@/lib/api";
import { useUIStore, useGenerationStore } from "@/lib/store";
import type { GenerateRequest } from "@/lib/types";

function formatApiError(e: ApiError): string {
  const detail = (e.body as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    const d = detail as {
      error: string;
      invalid_character_ids?: number[];
      invalid_location_id?: number | null;
    };
    if (d.error === "invalid_context") {
      return (
        `无效 ID：人物 ${d.invalid_character_ids?.join(", ") || "无"}；` +
        `地点 ${d.invalid_location_id ?? "无"}`
      );
    }
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return (detail[0] as { msg?: string }).msg ?? `HTTP ${e.status}`;
  }
  return `HTTP ${e.status}`;
}

export function useGenerate(chapterId: number) {
  const qc = useQueryClient();
  const setGenerationStatus = useUIStore((s) => s.setGenerationStatus);
  const chapterState = useGenerationStore(
    (s) => s.chapters[chapterId] ?? {
      events: [],
      generatedText: "",
      status: "idle" as const,
      error: null,
    }
  );
  const setChapter = useGenerationStore((s) => s.setChapter);
  const resetChapter = useGenerationStore((s) => s.resetChapter);
  const abortRef = useRef<AbortController | null>(null);
  const lastReqRef = useRef<GenerateRequest | null>(null);

  const start = useCallback(
    async (req: GenerateRequest) => {
      lastReqRef.current = req;
      setChapter(chapterId, {
        status: "preparing",
        events: [],
        generatedText: "",
        error: null,
      });
      setGenerationStatus("preparing");

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        for await (const ev of streamGeneration(chapterId, req, ac.signal)) {
          setChapter(chapterId, (prev) => {
            const patch: Partial<typeof prev> = {
              events: [...prev.events, ev],
            };
            if (ev.type === "token") {
              patch.generatedText = prev.generatedText + ev.text;
              patch.status = "streaming";
            } else if (ev.type === "done") {
              patch.status = "done";
            } else if (ev.type === "error") {
              patch.status = "error";
              patch.error = `${ev.message} (${ev.code})`;
            }
            return patch;
          });
          if (ev.type === "token") {
            setGenerationStatus("streaming");
          } else if (ev.type === "done") {
            setGenerationStatus("done");
            qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "project"] });
          } else if (ev.type === "error") {
            setGenerationStatus("error");
          }
        }
      } catch (e) {
        if (e instanceof ApiError) {
          // Capture full error info in shared state; caller can read state.error
          setChapter(chapterId, { status: "error", error: formatApiError(e) });
          setGenerationStatus("error");
        }
        // aborted — silent
      }
    },
    [chapterId, qc, setGenerationStatus, setChapter]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setChapter(chapterId, { status: "idle" });
    setGenerationStatus("idle");
  }, [chapterId, setChapter, setGenerationStatus]);

  const reset = useCallback(() => {
    resetChapter(chapterId);
    setGenerationStatus("idle");
  }, [chapterId, resetChapter, setGenerationStatus]);

  const retry = useCallback(() => {
    if (lastReqRef.current) {
      void start(lastReqRef.current);
    }
  }, [start]);

  return { ...chapterState, start, cancel, reset, retry };
}
