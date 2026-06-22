"use client";

import type { Editor } from "@tiptap/react";
import { usePolishStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";

// PolishButton only OPENS the modal (no API call). Same pattern as DiscussButton:
// the LLM call lives inside PolishModal because the user needs to specify a
// polish direction before the call (and may want to see the captured selection
// preview before firing it).
//
// If the user has text selected in the editor, that selection (text + range) is
// captured here and passed to PolishModal via the store. PolishModal then uses
// the range to replace exactly that slice on Accept.
export function PolishButton({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  // `chapterId` is accepted for API symmetry with other toolbar buttons but
  // not used here — PolishModal owns the API call (it already gets chapterId
  // from its own props).
  void chapterId;

  const handleClick = () => {
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
    usePolishStore.setState({
      polishModalOpen: true,
      polishResult: null,
      polishSelectedText: selectedText,
      polishSelectionFrom: from,
      polishSelectionTo: to,
    });
  };

  return (
    <Button variant="primary" onClick={handleClick}>
      ✨ 润色
    </Button>
  );
}
