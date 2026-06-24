"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { EventNode, type EventNodeData } from "./EventNode";
import type { Event } from "@/lib/types";

const nodeTypes: NodeTypes = { event: EventNode };

// Left-to-right layout: events grouped by chapter_order, laid out in columns
function computeLayout(events: Event[]): Map<number, { x: number; y: number }> {
  const positions = new Map<number, { x: number; y: number }>();

  // Group by chapter_order
  const byChapter = new Map<number, Event[]>();
  for (const e of events) {
    if (!byChapter.has(e.chapter_order)) byChapter.set(e.chapter_order, []);
    byChapter.get(e.chapter_order)!.push(e);
  }

  const sortedChapters = [...byChapter.keys()].sort((a, b) => a - b);
  const COL_WIDTH = 300;
  const ROW_HEIGHT = 120;

  sortedChapters.forEach((chOrder, colIdx) => {
    const chapterEvents = byChapter.get(chOrder)!;
    chapterEvents.forEach((e, rowIdx) => {
      positions.set(e.id, {
        x: colIdx * COL_WIDTH + 50,
        y: rowIdx * ROW_HEIGHT + 50,
      });
    });
  });

  return positions;
}

export function ForeshadowGraph({
  events,
  onEventClick,
}: {
  events: Event[];
  onEventClick?: (eventId: number) => void;
}) {
  const positions = useMemo(() => computeLayout(events), [events]);

  const nodes: Node[] = useMemo(() => {
    return events.map((e) => {
      const pos = positions.get(e.id) ?? { x: 0, y: 0 };
      return {
        id: String(e.id),
        type: "event",
        position: pos,
        data: {
          title: e.title,
          chapterTitle: e.chapter_title,
          chapterOrder: e.chapter_order,
          isUnpaid: e.is_unpaid,
          eventId: e.id,
        } as EventNodeData,
      };
    });
  }, [events, positions]);

  const edges: Edge[] = useMemo(() => {
    const edgeList: Edge[] = [];
    for (const e of events) {
      for (const targetId of e.foreshadows || []) {
        // Check if target event exists in our nodes
        const target = events.find((ev) => ev.id === targetId);
        if (!target) continue;

        const isPaidOff = (target.payoff_of || []).length > 0;
        edgeList.push({
          id: `e${e.id}-e${targetId}`,
          source: String(e.id),
          target: String(targetId),
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed },
          style: {
            stroke: isPaidOff ? "#22c55e" : "#ef4444",
            strokeWidth: 2,
            strokeDasharray: isPaidOff ? undefined : "5 5",
          },
          label: isPaidOff ? "已兑现" : "未兑现",
          labelStyle: { fontSize: 10, fill: isPaidOff ? "#22c55e" : "#ef4444" },
        });
      }
    }
    return edgeList;
  }, [events]);

  const onNodeClickHandler = useCallback<NodeMouseHandler>(
    (_, node) => {
      const data = node.data as EventNodeData;
      onEventClick?.(data.eventId);
    },
    [onEventClick],
  );

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-text-muted text-sm">还没有事件。完成一章后 AI 会自动抽取关键事件。</p>
      </div>
    );
  }

  // Check if any edges exist
  const hasEdges = edges.length > 0;

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClickHandler}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls position="bottom-right" />
        <MiniMap
          position="bottom-left"
          nodeColor={(node) => {
            const data = node.data as EventNodeData;
            return data.isUnpaid ? "#eab308" : "#6b7280";
          }}
          maskColor="rgba(0,0,0,0.1)"
          className="!bg-panel"
          pannable
          zoomable
        />
      </ReactFlow>
      {!hasEdges && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-panel border border-line rounded px-3 py-1 text-xs text-text-muted">
          暂无伏笔链接。在「列表」tab 中为事件添加 foreshadow 链接。
        </div>
      )}
    </div>
  );
}

export function ForeshadowGraphWrapper({
  events,
  onEventClick,
}: {
  events: Event[];
  onEventClick?: (eventId: number) => void;
}) {
  return (
    <ReactFlowProvider>
      <ForeshadowGraph events={events} onEventClick={onEventClick} />
    </ReactFlowProvider>
  );
}
