"use client";

import { formatReason } from "@/lib/versionReasons";
import type { ChapterVersionListItem } from "@/lib/types";

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(iso).toLocaleDateString();
}

export function VersionListItem({
  version,
  selected,
  onSelect,
}: {
  version: ChapterVersionListItem;
  selected: boolean;
  onSelect: (id: number) => void;
}) {
  const { icon, label } = formatReason(version.reason);
  const delta = version.delta_char_count;
  const deltaText =
    delta === 0
      ? "±0 字"
      : delta > 0
        ? `+${delta} 字`
        : `${delta} 字`;
  const deltaColor = delta > 0 ? "text-green-500" : delta < 0 ? "text-red-400" : "text-text-muted";

  return (
    <button
      type="button"
      onClick={() => onSelect(version.id)}
      className={`w-full text-left px-2 py-2 rounded text-sm flex flex-col gap-0.5 ${
        selected ? "bg-active text-white" : "hover:bg-hover text-text"
      }`}
    >
      <div className="flex items-center gap-2">
        <span>{icon}</span>
        <span className="flex-1 truncate">{label}</span>
        <span className={`text-xs ${selected ? "text-white/80" : deltaColor}`}>{deltaText}</span>
      </div>
      <div className={`text-xs ${selected ? "text-white/60" : "text-text-muted"}`}>
        {relativeTime(version.created_at)} · {version.char_count} 字
      </div>
    </button>
  );
}
