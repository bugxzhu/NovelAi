"use client";

import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamGeneration, type GenerationEvent } from "@/lib/sse";
import { ApiError } from "@/lib/api";
import { useUIStore } from "@/lib/store";
import type { GenerateRequest } from "@/lib/types";

export function useGenerate(chapterId: number) {
  const qc = useQueryClient();
  const setGenerationStatus = useUIStore((s) => s.setGenerationStatus);
  const [events, setEvents] = useState<GenerationEvent[]>([]);
  const [generatedText, setGeneratedText] = useState("");
  const [status, setStatus] = useState<
    "idle" | "preparing" | "streaming" | "done" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(
    async (req: GenerateRequest) => {
      setStatus("preparing");
      setGenerationStatus("preparing");
      setEvents([]);
      setGeneratedText("");
      setError(null);

      const ac = new AbortController();
      abortRef.current = ac;

      try {
        for await (const ev of streamGeneration(chapterId, req, ac.signal)) {
          setEvents((prev) => [...prev, ev]);
          if (ev.type === "token") {
            setGeneratedText((prev) => prev + ev.text);
            setStatus("streaming");
            setGenerationStatus("streaming");
          } else if (ev.type === "done") {
            setStatus("done");
            setGenerationStatus("done");
            qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "chapter", chapterId] });
            qc.invalidateQueries({ queryKey: ["generation-logs", "project"] });
          } else if (ev.type === "error") {
            setStatus("error");
            setGenerationStatus("error");
            setError(`${ev.message} (${ev.code})`);
          }
        }
      } catch (e) {
        if (e instanceof ApiError) {
          setStatus("error");
          setGenerationStatus("error");
          setError(`HTTP ${e.status}`);
          throw e;
        }
        // aborted — silent
      }
    },
    [chapterId, qc, setGenerationStatus]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setStatus("idle");
    setGenerationStatus("idle");
  }, [setGenerationStatus]);

  const reset = useCallback(() => {
    setEvents([]);
    setGeneratedText("");
    setStatus("idle");
    setError(null);
    setGenerationStatus("idle");
  }, [setGenerationStatus]);

  return { events, generatedText, status, error, start, cancel, reset };
}
