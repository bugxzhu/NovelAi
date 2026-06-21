"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { usePlotLines } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";
import { PlotLineForm } from "@/components/entities/PlotLineForm";

const STATUS_COLORS: Record<string, string> = {
  planned: "text-text-dim",
  active: "text-green-500",
  resolved: "text-blue-500",
  abandoned: "text-red-500",
};

export default function PlotLinesPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: plotLines = [], isLoading } = usePlotLines(pid);
  const [mode, setMode] = useState<"list" | "create">("list");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (plotLines ?? []).find((pl) => pl.id === selectedId);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="情节线"
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
          ) : !plotLines || plotLines.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有情节线</p>
          ) : (
            plotLines.map((pl) => (
              <button
                key={pl.id}
                onClick={() => {
                  setMode("list");
                  setSelectedId(pl.id);
                }}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === pl.id
                    ? "bg-active text-white"
                    : "hover:bg-hover text-text"
                }`}
              >
                📊 {pl.type === "main" ? "主线" : "支线"} · {pl.title}{" "}
                <span className={STATUS_COLORS[pl.status]}>({pl.status})</span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {mode === "create" ? (
            <PlotLineForm projectId={pid} />
          ) : selected ? (
            <PlotLineForm projectId={pid} plotLine={selected} />
          ) : (
            <div className="p-4 text-text-muted">请从左侧选择或新建情节线</div>
          )}
        </div>
      }
    />
  );
}
