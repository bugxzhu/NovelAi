import type { Editor } from "@tiptap/react";
import type { MarkdownStorage } from "tiptap-markdown";

/**
 * Read the current chapter content from the live TipTap editor as Markdown.
 * Returns "" if the editor isn't mounted yet (e.g., during chapter switch).
 *
 * Used by version-history snapshot triggers to capture the state BEFORE
 * a mutation handler runs (insertContent / setContent / etc).
 */
export function getCurrentChapterContent(): string {
  const editor = (window as unknown as { __chapterEditor?: Editor }).__chapterEditor;
  if (!editor) return "";
  const storage = (editor.storage as unknown as Record<string, unknown>).markdown as
    | MarkdownStorage
    | undefined;
  return storage?.getMarkdown() ?? "";
}
