"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface EventNodeData {
  title: string;
  chapterTitle: string;
  chapterOrder: number;
  isUnpaid: boolean;
  eventId: number;
  [key: string]: unknown;
}

export function EventNode({ data, selected }: NodeProps) {
  const d = data as EventNodeData;
  return (
    <div
      className={`bg-panel border rounded-lg px-3 py-2 min-w-[100px] max-w-[200px] cursor-pointer transition-shadow ${
        selected ? "border-accent ring-2 ring-accent/30"
        : d.isUnpaid ? "border-yellow-500/50"
        : "border-line"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-accent !w-2 !h-2 !border-0" />
      {d.isUnpaid && <div className="text-xs text-yellow-500 mb-1">⚠️ 未兑现</div>}
      <div className="text-sm font-bold text-text truncate">{d.title}</div>
      <div className="text-xs text-text-muted">第 {d.chapterOrder} 章</div>
      <Handle type="source" position={Position.Right} className="!bg-accent !w-2 !h-2 !border-0" />
    </div>
  );
}
