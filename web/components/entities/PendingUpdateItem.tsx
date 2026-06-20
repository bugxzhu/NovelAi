"use client";

import { Button } from "@/components/ui/Button";
import { useAcceptPendingUpdate, useRejectPendingUpdate } from "@/lib/queries";
import { loreTypeLabel } from "@/lib/types";
import type { PendingUpdateRead } from "@/lib/types";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function PendingUpdateItem({ pending }: { pending: PendingUpdateRead }) {
  const accept = useAcceptPendingUpdate();
  const reject = useRejectPendingUpdate();

  const isStateChange = pending.target_table === "character_states";
  const isRelationship = pending.target_table === "relationships";
  const isCharacter = pending.target_table === "characters";
  const isLore = pending.target_table === "lore_entries";

  // Header rendering
  let icon: string;
  let headerLabel: string;
  if (isStateChange) {
    icon = "📝";
    headerLabel = `状态变化 · ${pending.entity_name}`;
  } else if (isRelationship) {
    icon = "🤝";
    headerLabel = `关系变化 · ${pending.entity_name}`;
  } else {
    const entityLabel = isCharacter ? "人物" : "设定";
    const opLabel = pending.operation === "create" ? "新建" : "更新";
    icon = pending.operation === "create" ? "✏️" : "🔄";
    headerLabel = `${opLabel}${entityLabel} · ${pending.entity_name}${
      pending.field_name ? ` · ${pending.field_name}` : ""
    }`;
  }

  const handleReject = () => {
    const note = window.prompt("拒绝理由（可选）") ?? "";
    reject.mutate({ id: pending.id, note });
  };

  return (
    <div className="bg-panel border border-line rounded p-3 mb-2">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className="text-sm">
            <strong>{headerLabel}</strong>
          </span>
        </div>
        {isLore && pending.entity_type && (
          <span className="text-xs text-text-dim">[{loreTypeLabel(pending.entity_type)}]</span>
        )}
      </div>

      <div className="text-xs text-text-muted mb-2 pl-6">
        {isStateChange || isRelationship ? (
          <div>{pending.proposed_value}</div>
        ) : pending.field_name ? (
          <>
            <div>旧值：{pending.old_value || "(空)"}</div>
            <div>新值：{pending.proposed_value}</div>
          </>
        ) : (
          <div>{pending.proposed_value}</div>
        )}
      </div>

      {pending.reason && (
        <div className="text-xs text-text-dim pl-6 mb-2 italic">
          理由：{pending.reason}
        </div>
      )}

      {pending.status === "pending" ? (
        <div className="flex gap-2 pl-6">
          <Button
            variant="primary"
            onClick={() => accept.mutate(pending.id)}
            disabled={accept.isPending}
          >
            ✓ 接受
          </Button>
          <Button
            variant="ghost"
            onClick={handleReject}
            disabled={reject.isPending}
          >
            ✗ 拒绝
          </Button>
        </div>
      ) : (
        <div className="text-xs pl-6 text-text-dim">
          已{pending.status === "accepted" ? "接受" : "拒绝"}
          {` · ${formatTime(pending.updated_at)}`}
        </div>
      )}
    </div>
  );
}
