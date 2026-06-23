"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

export interface CharacterNodeData {
  name: string;
  role: string;
  charId: number;
  [key: string]: unknown;
}

export function CharacterNode({ data, selected }: NodeProps) {
  const d = data as CharacterNodeData;
  return (
    <div
      className={`bg-panel border rounded-lg px-3 py-2 text-center min-w-[80px] cursor-pointer transition-shadow ${
        selected ? "border-accent ring-2 ring-accent/30" : "border-line"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-accent !w-2 !h-2 !border-0" />
      <div className="text-base">👤</div>
      <div className="text-sm font-bold text-text">{d.name}</div>
      <div className="text-xs text-text-muted">{d.role}</div>
      <Handle type="source" position={Position.Bottom} className="!bg-accent !w-2 !h-2 !border-0" />
    </div>
  );
}
