"use client";

import { useEffect, useMemo, useRef } from "react";
import { useUpdateChapter } from "@/lib/queries";
import { debounce } from "@/lib/debounce";

export function useChapterAutosave(chapterId: number, projectId: number) {
  const mutation = useUpdateChapter(chapterId, projectId);

  // Capture the latest mutation in a ref so the debounced fn (created once) always
  // calls into the current closure rather than a stale one.
  const mutationRef = useRef(mutation);
  mutationRef.current = mutation;

  // Stable across renders — never recreated. This eliminates the stale-timer-fires-
  // into-stale-closure problem (review issue #4): the timer always invokes the
  // latest mutation via the ref.
  const debounced = useMemo(
    () =>
      debounce((content: string) => {
        mutationRef.current.mutate({ content });
      }, 500),
    []
  );

  // On unmount, flush (persist pending) rather than cancel (drop pending). This
  // prevents data loss when the user navigates away mid-debounce-window.
  useEffect(() => () => debounced.flush(), [debounced]);

  const saveNow = (content: string) => {
    debounced.flush();
    mutation.mutate({ content });
  };

  return { schedule: debounced, saveNow, mutation };
}
