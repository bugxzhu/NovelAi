"use client";

import { useState } from "react";
import { useCharacterStates } from "@/lib/queries";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function CharacterStateTimeline({ characterId }: { characterId: number | null }) {
  const [expanded, setExpanded] = useState(false);
  const { data: states = [], isLoading } = useCharacterStates(characterId);
  const count = states.length;

  if (characterId === null) {
    return (
      <div className="border-t border-line pt-3 mt-4">
        <p className="text-xs text-text-muted">
          暂无状态轨迹记录。完成章节后 Extractor 会自动抽取显著状态变化。
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-line pt-3 mt-4">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="text-sm text-text-muted-bright hover:text-text w-full text-left flex items-center gap-1"
      >
        <span>{expanded ? "▼" : "▶"}</span>
        <span>状态轨迹（{count} 条）</span>
      </button>

      {expanded && (
        <div className="mt-2 space-y-2">
          {isLoading ? (
            <p className="text-xs text-text-muted">加载中...</p>
          ) : count === 0 ? (
            <p className="text-xs text-text-muted">
              暂无状态轨迹记录。完成章节后 Extractor 会自动抽取显著状态变化。
            </p>
          ) : (
            states.map((s) => (
              <div
                key={s.id}
                className="border border-line rounded p-2 bg-input/30"
              >
                <div className="text-xs text-text-dim mb-1">
                  第 {s.chapter_order} 章 · {s.chapter_title}
                </div>
                <div className="text-sm text-text mb-1">
                  状态：<span>{s.state_snapshot}</span>
                </div>
                {s.change_summary && (
                  <div className="text-xs text-text-muted mb-1">
                    原因：{s.change_summary}
                  </div>
                )}
                <div className="text-[10px] text-text-dim">
                  抽取于 {formatTime(s.created_at)}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
