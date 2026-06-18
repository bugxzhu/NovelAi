"use client";

import Link from "next/link";
import type { Chapter } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  draft: "bg-[#666]",
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
  const wordCount = chapter.content?.length ?? 0;
  return (
    <Link
      href={href}
      className={`block px-3 py-2 rounded text-sm ${
        active ? "bg-[#37373d] text-white" : "hover:bg-[#2a2a2a] text-[#cccccc]"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_COLOR[chapter.status] ?? "bg-[#666]"}`} />
        <span className="flex-1 truncate">{chapter.title || `第 ${chapter.order_index} 章`}</span>
      </div>
      <div className="text-xs text-[#666] mt-0.5 pl-3.5">{wordCount} 字 · {chapter.status}</div>
    </Link>
  );
}
