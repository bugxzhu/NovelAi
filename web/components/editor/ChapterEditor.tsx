"use client";

import { useEffect, useRef } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import type { MarkdownStorage } from "tiptap-markdown";
import { extensions } from "./extensions";
import { EditorToolbar } from "./EditorToolbar";
import { FinalizeButton } from "./FinalizeButton";
import { ReviewButton } from "./ReviewButton";
import { ReviewModal } from "./ReviewModal";
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

export function ChapterEditor({
  chapter,
  onDelete,
}: {
  chapter: Chapter;
  onDelete?: () => void;
}) {
  const autosave = useChapterAutosave(chapter.id, chapter.project_id);
  // IME (中文输入法) composition state — skip onUpdate while user is mid-composition
  // to prevent stale pinyin characters from being serialized into Markdown, and to
  // avoid React re-renders disturbing the browser-locked DOM during composition.
  const isComposingRef = useRef(false);

  const editor = useEditor({
    extensions,
    content: chapter.content || "",
    onUpdate: ({ editor }) => {
      if (isComposingRef.current) return;
      autosave.schedule(getMarkdown(editor));
    },
    onBlur: ({ editor }) => {
      autosave.saveNow(getMarkdown(editor));
    },
    editorProps: {
      attributes: {
        class: "prose max-w-none focus:outline-none min-h-[60vh] p-8 font-serif leading-relaxed",
      },
      handleDOMEvents: {
        compositionstart: () => {
          isComposingRef.current = true;
          return false;
        },
        compositionend: () => {
          isComposingRef.current = false;
          // compositionend fires when user picks a candidate; the doc has the final
          // character(s) now. Use the outer-scope `editor` closure to schedule a save.
          if (editor) {
            autosave.schedule(getMarkdown(editor));
          }
          return false;
        },
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
      <EditorToolbar
        editor={editor}
        title={chapter.title}
        charCount={charCount}
        onDelete={onDelete}
        extraActions={
          <>
            <FinalizeButton chapterId={chapter.id} isFinal={chapter.status === "final"} />
            <ReviewButton chapterId={chapter.id} />
          </>
        }
      />
      <EditorContent editor={editor} className="flex-1 overflow-y-auto" />
      <ReviewModal chapterId={chapter.id} editor={editor} />
    </div>
  );
}
