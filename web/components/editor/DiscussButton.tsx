"use client";

import { useDiscussStore } from "@/lib/store";

// Different from ReviewButton: this only OPENS the modal. The LLM call and
// question input live inside DiscussModal, because Discuss requires user input
// (a question) before the API call can be made. ReviewButton was a one-click
// button because review takes no parameters.
export function DiscussButton({ chapterId }: { chapterId: number }) {
  return (
    <button
      onClick={() => useDiscussStore.setState({ modalOpenFor: chapterId })}
      className="px-3 py-1.5 rounded text-sm bg-accent hover:bg-accent-hover text-white"
    >
      💬 探讨
    </button>
  );
}
