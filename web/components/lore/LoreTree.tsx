"use client";

import { useState } from "react";
import type { LoreEntry } from "@/lib/types";

const TYPE_ICONS: Record<string, string> = {
  location: "📍",
  faction: "⚔️",
  item: "🗡️",
  organization: "🏛️",
  concept: "💡",
  custom: "📦",
};

interface TreeNodeProps {
  entry: LoreEntry;
  allEntries: LoreEntry[];
  level: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function TreeNode({ entry, allEntries, level, selectedId, onSelect }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(true);
  const children = allEntries.filter((e) => e.parent_id === entry.id);
  const hasChildren = children.length > 0;
  const isSelected = entry.id === selectedId;

  return (
    <div>
      <div
        className={`flex items-center gap-1 px-2 py-1 rounded cursor-pointer text-sm ${
          isSelected ? "bg-active text-white" : "hover:bg-hover text-text"
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => onSelect(entry.id)}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="w-4 h-4 flex items-center justify-center text-xs text-text-muted hover:text-text shrink-0"
          >
            {expanded ? "▼" : "▶"}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}
        <span className="shrink-0">{TYPE_ICONS[entry.type] || "📦"}</span>
        <span className="truncate">{entry.name || "未命名"}</span>
        {entry.description && (
          <span
            className={`text-xs truncate ${
              isSelected ? "text-white/60" : "text-text-dim"
            }`}
          >
            — {entry.description.slice(0, 30)}
            {entry.description.length > 30 ? "..." : ""}
          </span>
        )}
      </div>
      {hasChildren && expanded && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              entry={child}
              allEntries={allEntries}
              level={level + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function LoreTree({
  entries,
  selectedId,
  onSelect,
}: {
  entries: LoreEntry[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  // Root entries: parent_id is null
  const roots = entries.filter((e) => !e.parent_id);
  // Orphan entries: parent_id is set but parent doesn't exist
  const orphans = entries.filter(
    (e) => e.parent_id && !entries.some((p) => p.id === e.parent_id),
  );

  if (entries.length === 0) {
    return (
      <p className="text-xs text-text-muted p-2">
        还没有设定。点击&quot;+ 新建&quot;添加地点、势力、物品等。
      </p>
    );
  }

  return (
    <div className="space-y-0.5">
      {roots.map((entry) => (
        <TreeNode
          key={entry.id}
          entry={entry}
          allEntries={entries}
          level={0}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
      {orphans.length > 0 && (
        <>
          <div className="text-xs text-text-dim px-2 py-1 mt-2">（父级已删除）</div>
          {orphans.map((entry) => (
            <TreeNode
              key={entry.id}
              entry={entry}
              allEntries={entries}
              level={0}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </>
      )}
    </div>
  );
}
