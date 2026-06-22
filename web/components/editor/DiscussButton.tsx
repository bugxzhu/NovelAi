"use client";

import type { Editor } from "@tiptap/react";
import { useDiscussStore } from "@/lib/store";

// Different from ReviewButton: this only OPENS the modal. The LLM call and
// question input live inside DiscussModal, because Discuss requires user input
// (a question) before the API call can be made. ReviewButton was a one-click
// button because review takes no parameters.
//
// If the user has text selected in the editor, that selection is captured and
// passed to DiscussModal as the discussion focus.
export function DiscussButton({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  const handleClick = () => {
    // Check if user has text selected in the editor
    let selectedText = "";
    if (editor) {
      const { from, to, empty } = editor.state.selection;
      if (!empty) {
        selectedText = editor.state.doc.textBetween(from, to, "\n");
      }
    }
    useDiscussStore.setState({
      modalOpenFor: chapterId,
      selectedText,
    });
  };

  return (
    <button
      onClick={handleClick}
      className="px-3 py-1.5 rounded text-sm bg-accent hover:bg-accent-hover text-white"
    >
      💬 探讨
    </button>
  );
}
