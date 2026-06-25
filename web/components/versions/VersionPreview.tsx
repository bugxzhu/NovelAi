"use client";

import type { ChapterVersionRead } from "@/lib/types";
import { formatReason } from "@/lib/versionReasons";

export function VersionPreview({
  version,
  loading,
}: {
  version: ChapterVersionRead | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-text-muted text-sm">加载中...</p>
      </div>
    );
  }
  if (!version) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-text-muted text-sm">从左侧选择一个版本查看内容</p>
      </div>
    );
  }

  const { icon, label } = formatReason(version.reason);

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-4 py-2 border-b border-line bg-panel">
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className="text-sm text-text">{label}</span>
          <span className="text-xs text-text-muted ml-auto">
            {version.char_count} 字 · {new Date(version.created_at).toLocaleString()}
          </span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-8">
        <pre className="whitespace-pre-wrap font-serif text-base leading-relaxed text-text">
          {version.content ?? "(无内容)"}
        </pre>
      </div>
    </div>
  );
}
