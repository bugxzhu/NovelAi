"use client";

import { useState } from "react";
import type { Editor } from "@tiptap/react";
import { api, ApiError } from "@/lib/api";
import { usePolishStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";

// One-click polish: captures the editor selection (if any) at click time and
// fires the API call immediately. Unlike DiscussButton (which only opens a
// modal because discuss needs a question input first), polish has no user
// input before the call — the user clicks, waits, sees the result, accepts
// or rejects.
//
// The captured selection range (from/to) is stored so PolishModal can replace
// exactly that range when the user accepts. For whole-chapter polish (no
// selection), Accept replaces all editor content.
export function PolishButton({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  const toast = useToast();
  const setResult = usePolishStore((s) => s.setResult);
  const setSelectionRange = usePolishStore((s) => s.setSelectionRange);
  const [state, setState] = useState<"idle" | "polishing">("idle");

  const handleClick = async () => {
    let selectedText = "";
    let from: number | null = null;
    let to: number | null = null;
    if (editor) {
      const sel = editor.state.selection;
      if (!sel.empty) {
        selectedText = editor.state.doc.textBetween(sel.from, sel.to, "\n");
        from = sel.from;
        to = sel.to;
      }
    }

    // Stash both the selected text (for the modal's "原文" preview) and the
    // ProseMirror range (for Accept-time replacement).
    usePolishStore.setState({ selectedText });
    if (from != null && to != null) {
      setSelectionRange(from, to);
    } else {
      // Reset any stale range from a previous click.
      usePolishStore.setState({ selectionFrom: null, selectionTo: null });
    }

    setState("polishing");
    try {
      const r = await api.polishChapter(chapterId, selectedText || undefined);
      setResult(r);
      toast("润色完成", "success");
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${JSON.stringify(e.body)}`
        : (e as Error).message;
      toast(`润色失败: ${msg}`, "error");
    } finally {
      setState("idle");
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleClick}
      disabled={state === "polishing"}
    >
      {state === "polishing" ? "⏳ 润色中..." : "✨ 润色"}
    </Button>
  );
}
