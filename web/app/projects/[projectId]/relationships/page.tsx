"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useRelationships, useCharacters } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { RelationshipForm } from "@/components/entities/RelationshipForm";
import { RelationshipHistoryPanel } from "@/components/entities/RelationshipHistoryPanel";
import { RelationshipGraphWrapper } from "@/components/relationships/RelationshipGraph";

export default function RelationshipsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: relationships, isLoading } = useRelationships(pid);
  const { data: characters } = useCharacters(pid);
  const [tab, setTab] = useState<"graph" | "list">("graph");
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
                setTab("list");
              }}
            >
              + 新建
            </Button>
          }
        >
          {/* Tab buttons */}
          <div className="flex gap-1 mb-3 px-1">
            <button
              onClick={() => setTab("graph")}
              className={`text-xs px-3 py-1 rounded ${
                tab === "graph" ? "bg-active text-white" : "text-text-muted hover:bg-hover"
              }`}
            >
              图谱
            </button>
            <button
              onClick={() => setTab("list")}
              className={`text-xs px-3 py-1 rounded ${
                tab === "list" ? "bg-active text-white" : "text-text-muted hover:bg-hover"
              }`}
            >
              列表
            </button>
          </div>

          {tab === "list" ? (
            isLoading ? (
              <p className="text-xs text-text-muted p-2">加载中...</p>
            ) : !relationships || relationships.length === 0 ? (
              <p className="text-xs text-text-muted p-2">
                还没有关系。点击&quot;+ 新建&quot;建立人物之间的关系（仇人/朋友/恋人等）。
              </p>
            ) : (
              relationships.map((r) => (
                <button
                  key={r.id}
                  onClick={() => {
                    setMode("list");
                    setSelectedId(r.id);
                  }}
                  className={`block w-full text-left px-3 py-2 rounded text-sm ${
                    selectedId === r.id ? "bg-active text-white" : "hover:bg-hover text-text"
                  }`}
                >
                  {r.from_char_name} → {r.to_char_name}{" "}
                  <span className="text-text-muted">
                    · {r.type}（{r.strength}）
                  </span>
                </button>
              ))
            )
          ) : (
            <p className="text-xs text-text-muted px-2 py-1">
              {relationships?.length ?? 0} 条关系 · {characters?.length ?? 0} 个人物
            </p>
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-hidden">
          {tab === "graph" ? (
            <RelationshipGraphWrapper
              relationships={relationships ?? []}
              characters={characters ?? []}
              projectId={pid}
            />
          ) : mode === "create" ? (
            <div className="h-full overflow-y-auto">
              <RelationshipForm projectId={pid} />
            </div>
          ) : selected ? (
            <div className="h-full overflow-y-auto">
              <RelationshipForm projectId={pid} relationship={selected} />
              <RelationshipHistoryPanel
                fromId={selected.from_char_id}
                toId={selected.to_char_id}
              />
            </div>
          ) : (
            <div className="p-4 text-text-muted">
              请从左侧选择或新建关系，或点击&quot;+ 新建&quot;建立第一条关系。
            </div>
          )}
        </div>
      }
    />
  );
}
