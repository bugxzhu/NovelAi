"use client";

import { useRelationshipHistory } from "@/lib/queries";

export function RelationshipHistoryPanel({
  fromId,
  toId,
}: {
  fromId: number | null;
  toId: number | null;
}) {
  const { data: history = [], isLoading } = useRelationshipHistory(fromId, toId);

  if (fromId === null || toId === null) {
    return (
      <div className="border-t border-line pt-3 mt-4">
        <p className="text-xs text-text-muted">暂无演变历史</p>
      </div>
    );
  }

  return (
    <div className="border-t border-line pt-3 mt-4">
      <div className="text-sm text-text-muted-bright mb-2">
        ▼ 演变历史（{history.length} 版本）
      </div>
      {isLoading ? (
        <p className="text-xs text-text-muted">加载中...</p>
      ) : history.length === 0 ? (
        <p className="text-xs text-text-muted">暂无演变历史</p>
      ) : (
        <div className="space-y-2">
          {history.map((h) => {
            const range = h.valid_to_chapter === null
              ? `第 ${h.valid_from_chapter} 章 → 当前`
              : `第 ${h.valid_from_chapter} 章 → 第 ${h.valid_to_chapter} 章`;
            return (
              <div
                key={h.version_id}
                className="border border-line rounded p-2 bg-input/30"
              >
                <div className="text-xs text-text-dim mb-1">{range}</div>
                <div className="text-sm text-text mb-1">
                  <span>{h.type}</span>（强度 {h.strength}）
                </div>
                {h.description && (
                  <div className="text-xs text-text-muted mb-1">{h.description}</div>
                )}
                {h.change_summary && (
                  <div className="text-xs text-text-muted mb-1">
                    原因：{h.change_summary}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
