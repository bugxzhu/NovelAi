"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useStoryMilestones } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { MilestoneForm } from "@/components/entities/MilestoneForm";
import type { StoryMilestone } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  planned: "text-text-dim",
  written: "text-green-500",
  needs_revision: "text-yellow-500",
};

function chapterRange(m: StoryMilestone): string {
  const s = m.chapter_start;
  const e = m.chapter_end;
  if (s == null && e == null) return "";
  if (s != null && e != null) return `第 ${s}-${e} 章`;
  if (s != null) return `第 ${s} 章起`;
  return `至第 ${e} 章`;
}

export default function OutlinePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: milestones = [], isLoading } = useStoryMilestones(pid);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const sorted = [...(milestones ?? [])].sort((a, b) => a.order_index - b.order_index);
  const selected = sorted.find((m) => m.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="蓝图"
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
          ) : sorted.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有里程碑</p>
          ) : (
            sorted.map((m) => {
              const range = chapterRange(m);
              return (
                <button
                  key={m.id}
                  onClick={() => {
                    setMode("list");
                    setSelectedId(m.id);
                  }}
                  className={`block w-full text-left px-3 py-2 rounded text-sm ${
                    selectedId === m.id
                      ? "bg-active text-white"
                      : "hover:bg-hover text-text"
                  }`}
                >
                  🗺️ <span className={STATUS_COLORS[m.status]}>({m.status})</span>{" "}
                  {m.title}（{m.type}
                  {range ? `，${range}` : ""}）
                </button>
              );
            })
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <MilestoneForm projectId={pid} />
          ) : selected ? (
            <MilestoneForm projectId={pid} milestone={selected} />
          ) : (
            <div className="p-4 text-text-muted">请从左侧选择或新建里程碑</div>
          )}
        </div>
      }
    />
  );
}
