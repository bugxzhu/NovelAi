"use client";

import type { Editor } from "@tiptap/react";

export function EditorToolbar({
  editor,
  title,
  charCount,
}: {
  editor: Editor | null;
  title: string;
  charCount: number;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-[#3c3c3c] bg-[#252526]">
      <span className="text-sm text-[#cccccc] truncate max-w-md">{title || "未命名章节"}</span>
      <span className="text-xs text-[#888]">{charCount} 字</span>
    </div>
  );
}
