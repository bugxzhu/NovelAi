"use client";

import { useState } from "react";
import type { Event, EventFilter } from "@/lib/types";

const FILTERS: Array<{ key: EventFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "unpaid", label: "未兑现伏笔 ⚠️" },
  { key: "paid", label: "已兑现 ✓" },
];

export function EventList({
  events,
  selectedId,
  onSelect,
  onFilterChange,
}: {
  events: Event[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onFilterChange: (f: EventFilter) => void;
}) {
  const [filter, setFilter] = useState<EventFilter>("all");

  const handleChange = (f: EventFilter) => {
    setFilter(f);
    onFilterChange(f);
  };

  // Group by chapter_order
  const byChapter = new Map<number, Event[]>();
  for (const e of events) {
    if (!byChapter.has(e.chapter_order)) byChapter.set(e.chapter_order, []);
    byChapter.get(e.chapter_order)!.push(e);
  }
  const sortedChapters = [...byChapter.keys()].sort((a, b) => a - b);

  return (
    <div>
      {/* Filter tabs */}
      <div className="flex gap-2 mb-3 px-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => handleChange(f.key)}
            className={`text-xs px-2 py-1 rounded ${
              filter === f.key
                ? "bg-active text-white"
                : "text-text-muted hover:bg-hover"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {sortedChapters.length === 0 ? (
        <p className="text-xs text-text-muted p-2">
          还没有事件。完成一章后 AI 会自动抽取关键事件，或点击&quot;+ 新建&quot;手动添加。
        </p>
      ) : (
        sortedChapters.map((order) => (
          <div key={order} className="mb-3">
            <div className="text-xs text-text-dim px-3 py-1">
              第 {order} 章
            </div>
            {(byChapter.get(order) || []).map((e) => (
              <button
                key={e.id}
                onClick={() => onSelect(e.id)}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === e.id
                    ? "bg-active text-white"
                    : "hover:bg-hover text-text"
                }`}
              >
                {e.is_unpaid && <span className="text-yellow-500">⚠️ </span>}
                🎯 {e.title}
                  {e.involved_character_names.length > 0 && (
                    <span className="text-text-muted">
                      {" "}· {e.involved_character_names.join("、")}
                    </span>
                  )}
                  {e.location_name && (
                    <span className="text-text-muted"> @{e.location_name}</span>
                  )}
                </button>
              ))}
          </div>
        ))
      )}
    </div>
  );
}
