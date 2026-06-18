"use client";

import { useEffect, useRef } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import { extensions } from "./extensions";
import { EditorToolbar } from "./EditorToolbar";
import { useChapterAutosave } from "./useChapterAutosave";
import type { Chapter } from "@/lib/types";

// Type augmentation: tiptap-markdown ships no TypeScript types, so declare
// the storage shape manually. `getMarkdown()` returns the current document
// serialized as a Markdown string.
declare module "@tiptap/core" {
  interface Storage {
    markdown?: {
      getMarkdown: () => string;
    };
  }
}

function getMarkdown(editor: Editor): string {
  return editor.storage.markdown?.getMarkdown() ?? "";
}

export function ChapterEditor({ chapter }: { chapter: Chapter }) {
  const autosave = useChapterAutosave(chapter.id, chapter.project_id);
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null);

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
        class: "prose prose-invert max-w-none focus:outline-none min-h-[60vh] p-8 font-serif leading-relaxed",
      },
    },
  });

  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  // Expose imperative API for "accept generated text" insertion (StreamView uses this in Task 13)
  useEffect(() => {
    (window as unknown as { __chapterEditor: typeof editor }).__chapterEditor = editor;
    return () => {
      delete (window as unknown as { __chapterEditor?: typeof editor }).__chapterEditor;
    };
  }, [editor]);

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
