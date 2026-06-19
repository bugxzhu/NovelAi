"use client";

import type { Editor } from "@tiptap/react";

export function EditorToolbar({
  editor,
  title,
  charCount,
  onDelete,
}: {
  editor: Editor | null;
  title: string;
  charCount: number;
  onDelete?: () => void;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-line bg-panel">
      <span className="text-sm text-text truncate max-w-md">{title || "未命名章节"}</span>
      <div className="flex items-center gap-3">
        <span className="text-xs text-text-muted">{charCount} 字</span>
        {onDelete && (
          <button
            onClick={onDelete}
            title="删除章节"
            className="text-xs text-text-muted hover:text-text"
          >
            🗑️
          </button>
        )}
      </div>
    </div>
  );
}
