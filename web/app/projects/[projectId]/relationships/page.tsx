"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useRelationships } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { RelationshipForm } from "@/components/entities/RelationshipForm";
import { RelationshipHistoryPanel } from "@/components/entities/RelationshipHistoryPanel";

export default function RelationshipsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: relationships, isLoading } = useRelationships(pid);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (relationships ?? []).find((r) => r.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="关系"
          action={
            <Button
              variant="ghost"
              onClick={() => {
                setMode("create");
                setSelectedId(null);
              }}
            >
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : !relationships || relationships.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有关系</p>
          ) : (
            relationships.map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  setMode("list");
                  setSelectedId(r.id);
                }}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === r.id
                    ? "bg-active text-white"
                    : "hover:bg-hover text-text"
                }`}
              >
                {r.from_char_name} → {r.to_char_name}{" "}
                <span className="text-text-muted">
                  · {r.type}（{r.strength}）
                </span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <RelationshipForm projectId={pid} />
          ) : selected ? (
            <div>
              <RelationshipForm projectId={pid} relationship={selected} />
              <RelationshipHistoryPanel
                fromId={selected.from_char_id}
                toId={selected.to_char_id}
              />
            </div>
          ) : (
            <div className="p-4 text-text-muted">请从左侧选择或新建关系</div>
          )}
        </div>
      }
    />
  );
}
