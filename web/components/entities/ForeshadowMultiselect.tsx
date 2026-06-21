"use client";

import { useState } from "react";
import { useUpdateEvent } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";
import type { Event } from "@/lib/types";

export function ForeshadowMultiselect({
  event,
  allEvents,
}: {
  event: Event;
  allEvents: Event[];
}) {
  const update = useUpdateEvent(event.id, event.project_id);
  const toast = useToast();
  const [adding, setAdding] = useState(false);

  // Candidates: events in same project, not self, not already selected
  const candidates = allEvents.filter(
    (e) => e.id !== event.id && !(event.foreshadows || []).includes(e.id)
  );

  const handleAdd = async (targetId: number) => {
    const next = [...(event.foreshadows || []), targetId];
    try {
      await update.mutateAsync({ foreshadows: next });
      toast("已添加伏笔链接", "success");
    } catch (e) {
      toast(`添加失败: ${(e as Error).message}`, "error");
    }
    setAdding(false);
  };

  const handleRemove = async (targetId: number) => {
    const next = (event.foreshadows || []).filter((i) => i !== targetId);
    try {
      await update.mutateAsync({ foreshadows: next });
      toast("已移除伏笔链接", "success");
    } catch (e) {
      toast(`移除失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <div className="border-t border-line pt-3 mt-4">
      <div className="text-sm text-text-muted-bright mb-2">▼ 伏笔链接</div>

      {/* Forward: this event foreshadows these events (editable) */}
      <div className="mb-3">
        <div className="text-xs text-text-muted mb-1">此事件是以下事件的伏笔：</div>
        {(event.foreshadows || []).length === 0 ? (
          <div className="text-xs text-text-dim">（无）</div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {(event.foreshadows || []).map((tid) => {
              const target = allEvents.find((e) => e.id === tid);
              if (!target) return null;
              return (
                <span
                  key={tid}
                  className="inline-flex items-center gap-1 bg-input border border-line rounded px-2 py-0.5 text-xs"
                >
                  第 {target.chapter_order} 章 · {target.title}
                  <button
                    type="button"
                    onClick={() => handleRemove(tid)}
                    className="text-text-dim hover:text-danger"
                    disabled={update.isPending}
                  >
                    ✗
                  </button>
                </span>
              );
            })}
          </div>
        )}
        {!adding && candidates.length > 0 && (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="text-xs text-text-muted hover:text-text mt-1"
          >
            + 添加目标事件
          </button>
        )}
        {adding && (
          <select
            autoFocus
            value=""
            onChange={(e) => {
              if (e.target.value) handleAdd(Number(e.target.value));
            }}
            onBlur={() => setAdding(false)}
            className="block w-full mt-1 bg-input border border-line rounded p-1 text-xs"
          >
            <option value="">选择目标事件...</option>
            {candidates.map((e) => (
              <option key={e.id} value={e.id}>
                第 {e.chapter_order} 章 · {e.title}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Reverse: which events foreshadow this one (read-only derived) */}
      <div>
        <div className="text-xs text-text-muted mb-1">此事件兑现了以下伏笔：</div>
        {(event.payoff_of || []).length === 0 ? (
          <div className="text-xs text-text-dim">（无）</div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {(event.payoff_of || []).map((pid, idx) => (
              <span
                key={pid}
                className="inline-flex items-center gap-1 bg-input/50 border border-line rounded px-2 py-0.5 text-xs text-text-muted"
              >
                {event.payoff_of_titles?.[idx] || `#${pid}`}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
