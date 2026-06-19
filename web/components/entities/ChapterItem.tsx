"use client";

import Link from "next/link";
import { useState } from "react";
import type { Chapter } from "@/lib/types";
import { useUpdateChapter } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-text-dim",
  writing: "bg-yellow-600",
  reviewed: "bg-blue-600",
  final: "bg-green-600",
};

export function ChapterItem({
  chapter,
  href,
  active,
}: {
  chapter: Chapter;
  href: string;
  active: boolean;
}) {
  const update = useUpdateChapter(chapter.id, chapter.project_id);
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(chapter.title);
  const wordCount = chapter.content?.length ?? 0;

  const save = () => {
    const trimmed = title.trim();
    if (!trimmed || trimmed === chapter.title) {
      setTitle(chapter.title);
      setEditing(false);
      return;
    }
    update.mutate(
      { title: trimmed },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
      }
    );
  };

  if (editing) {
    return (
      <div className="px-3 py-2 rounded text-sm bg-active">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={save}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") {
              setTitle(chapter.title);
              setEditing(false);
            }
          }}
          className="w-full bg-input border border-accent rounded px-2 py-0.5 text-text text-sm"
        />
        <div className="text-xs text-text-muted mt-1">回车保存 · Esc 取消</div>
      </div>
    );
  }

  return (
    <div className="relative group">
      <Link
        href={href}
        className={`block px-3 py-2 rounded text-sm ${
          active ? "bg-active text-white" : "hover:bg-hover text-text"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLOR[chapter.status] ?? "bg-text-dim"}`} />
          <span className="flex-1 truncate">{chapter.title || `第 ${chapter.order_index} 章`}</span>
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setEditing(true);
            }}
            title="重命名"
            className="hidden group-hover:flex w-5 h-5 items-center justify-center rounded text-xs hover:bg-button-hover text-text-muted"
          >
            ✏️
          </button>
        </div>
        <div className="text-xs text-text-dim mt-0.5 pl-3.5">{wordCount} 字 · {chapter.status}</div>
      </Link>
    </div>
  );
}
