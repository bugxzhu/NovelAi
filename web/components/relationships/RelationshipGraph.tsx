"use client";

import { useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
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

import { CharacterNode, type CharacterNodeData } from "./CharacterNode";
import type { Character, Relationship } from "@/lib/types";

const RADIUS = 250;
const CENTER = { x: 400, y: 300 };

function circleLayout(index: number, total: number) {
  if (total <= 1) return CENTER;
  const angle = (2 * Math.PI * index) / total;
  return {
    x: CENTER.x + RADIUS * Math.cos(angle),
    y: CENTER.y + RADIUS * Math.sin(angle),
  };
}

function strengthToColor(s: number): string {
  if (s < -0.5) return "#ef4444";
  if (s < 0) return "#f59e0b";
  if (s < 0.5) return "#6b7280";
  return "#22c55e";
}

function strengthToWidth(s: number): number {
  const abs = Math.abs(s);
  return Math.max(1.5, abs * 3.5);
}

const nodeTypes: NodeTypes = { character: CharacterNode };

export function RelationshipGraph({
  relationships,
  characters,
  projectId,
}: {
  relationships: Relationship[];
  characters: Character[];
  projectId: number;
}) {
  const router = useRouter();

  const nodes: Node[] = useMemo(() => {
    return characters.map((c, i) => {
      const pos = circleLayout(i, characters.length);
      return {
        id: String(c.id),
        type: "character",
        position: pos,
        data: {
          name: c.name,
          role: c.role,
          charId: c.id,
        } as CharacterNodeData,
      };
    });
  }, [characters]);

  const edges: Edge[] = useMemo(() => {
    return relationships.map((r) => ({
      id: String(r.id),
      source: String(r.from_char_id),
      target: String(r.to_char_id),
      type: "smoothstep",
      label: r.type,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: strengthToColor(r.strength),
        strokeWidth: strengthToWidth(r.strength),
      },
      data: {
        strength: r.strength,
        description: r.description,
      },
    }));
  }, [relationships]);

  const onNodeClick = useCallback<NodeMouseHandler>(
    (_, node) => {
      const data = node.data as CharacterNodeData;
      sessionStorage.setItem("selectCharId", String(data.charId));
      router.push(`/projects/${projectId}/characters`);
    },
    [router, projectId],
  );

  if (characters.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-text-muted text-sm">还没有人物，先去 👥 人物页创建角色。</p>
      </div>
    );
  }

  if (relationships.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-text-muted text-sm">还没有关系。切换到「列表」tab 新建关系。</p>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls position="bottom-right" />
        <MiniMap
          position="bottom-left"
          nodeColor="#6b7280"
          maskColor="rgba(0,0,0,0.1)"
          className="!bg-panel"
          pannable
          zoomable
        />
      </ReactFlow>
    </div>
  );
}

export function RelationshipGraphWrapper(props: {
  relationships: Relationship[];
  characters: Character[];
  projectId: number;
}) {
  return (
    <ReactFlowProvider>
      <RelationshipGraph {...props} />
    </ReactFlowProvider>
  );
}
