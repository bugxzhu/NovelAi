"use client";

import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import type { MarkdownStorage } from "tiptap-markdown";
import { extensions } from "./extensions";
import { EditorToolbar } from "./EditorToolbar";
import { useChapterAutosave } from "./useChapterAutosave";
import type { Chapter } from "@/lib/types";

// TipTap's `Storage` is a generic record and does not auto-merge per-extension
// storage, so we cast the `markdown` namespace to the package's own typed shape.
function getMarkdown(editor: Editor): string {
  const storage = (editor.storage as unknown as Record<string, unknown>).markdown as
    | MarkdownStorage
    | undefined;
  return storage?.getMarkdown() ?? "";
}

export function ChapterEditor({ chapter }: { chapter: Chapter }) {
  const autosave = useChapterAutosave(chapter.id, chapter.project_id);

  const editor = useEditor({
    extensions,
    content: chapter.content || "",
    onUpdate: ({ editor }) => {
      autosave.schedule(getMarkdown(editor));
    },
    onBlur: ({ editor }) => {
      autosave.saveNow(getMarkdown(editor));
    },
    editorProps: {
      attributes: {
        class: "prose max-w-none focus:outline-none min-h-[60vh] p-8 font-serif leading-relaxed",
      },
    },
  });

  // Expose imperative API for "accept generated text" insertion (StreamView uses this in Task 13)
  useEffect(() => {
    (window as unknown as { __chapterEditor: typeof editor }).__chapterEditor = editor;
    return () => {
      delete (window as unknown as { __chapterEditor?: typeof editor }).__chapterEditor;
    };
  }, [editor]);

  // Flush pending saves of the previous chapter before its editor content is reset.
  // The cleanup of the previous render runs with the OLD editor still showing OLD content,
  // so getMarkdown() captures whatever the user typed but hadn't yet persisted.
  useEffect(() => {
    return () => {
      if (editor) {
        autosave.saveNow(getMarkdown(editor));
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter.id]);

  // Reset content when chapter changes
  useEffect(() => {
    if (editor && chapter.content !== undefined) {
      const current = getMarkdown(editor);
      if (current !== chapter.content) {
        editor.commands.setContent(chapter.content || "", { emitUpdate: false });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapter.id]);

  const charCount = editor?.storage.characterCount?.characters?.() ?? 0;

  return (
    <div className="flex flex-col h-full">
      <EditorToolbar editor={editor} title={chapter.title} charCount={charCount} />
      <EditorContent editor={editor} className="flex-1 overflow-y-auto" />
    </div>
  );
}
