"use client";

import { useEffect, useMemo, useRef } from "react";
import { useUpdateChapter } from "@/lib/queries";
import { debounce } from "@/lib/debounce";

export function useChapterAutosave(chapterId: number, projectId: number) {
  const mutation = useUpdateChapter(chapterId, projectId);
  const debounced = useMemo(
    () =>
      debounce((content: string) => {
        mutation.mutate({ content });
      }, 500),
    [mutation, chapterId]
  );
  const ref = useRef(debounced);
  ref.current = debounced;

  useEffect(() => () => ref.current.cancel(), []);

  const saveNow = (content: string) => {
    ref.current.flush();
    mutation.mutate({ content });
  };

  return { schedule: debounced, saveNow, mutation };
}
