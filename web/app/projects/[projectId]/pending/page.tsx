"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useChapters, usePendingUpdates } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { PendingUpdateItem } from "@/components/entities/PendingUpdateItem";
import type { PendingStatus } from "@/lib/types";

const STATUS_TABS: Array<{ key: PendingStatus; label: string }> = [
  { key: "pending", label: "待处理" },
  { key: "accepted", label: "已接受" },
  { key: "rejected", label: "已拒绝" },
  { key: "all", label: "全部" },
];

export default function PendingPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [status, setStatus] = useState<PendingStatus>("pending");
  const [chapterFilter, setChapterFilter] = useState<number | "">("");
  const { data: chapters } = useChapters(pid);
  const { data: pendings, isLoading } = usePendingUpdates(
    pid,
    status,
    chapterFilter || undefined
  );

  const chapterTitle = (cid: number) =>
    chapters?.find((c) => c.id === cid)?.title ?? `Chapter ${cid}`;

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="待处理">
          <div className="px-1 mb-2">
            <div className="text-xs text-text-muted mb-1">状态</div>
            <div className="flex flex-wrap gap-1">
              {STATUS_TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setStatus(t.key)}
                  className={`px-2 py-0.5 rounded text-xs ${
                    status === t.key
                      ? "bg-accent text-white"
                      : "bg-button text-text hover:bg-button-hover"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-1 mb-2">
            <div className="text-xs text-text-muted mb-1">章节</div>
            <select
              value={chapterFilter}
              onChange={(e) =>
                setChapterFilter(e.target.value ? Number(e.target.value) : "")
              }
              className="bg-input border border-line rounded p-1 text-text w-full"
            >
              <option value="">全部章节</option>
              {(chapters ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title || `第 ${c.order_index} 章`}
                </option>
              ))}
            </select>
          </div>
          <div className="text-xs text-text-dim px-2 mt-4">
            {isLoading ? "加载中..." : `共 ${pendings?.length ?? 0} 条`}
          </div>
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4">
          {isLoading ? (
            <p className="text-text-muted">加载中...</p>
          ) : !pendings || pendings.length === 0 ? (
            <p className="text-text-muted">无符合条件的记录</p>
          ) : (
            <div className="max-w-3xl mx-auto">
              {pendings.map((p) => (
                <div key={p.id}>
                  <div className="text-xs text-text-dim mt-3 mb-1">
                    {chapterTitle(p.chapter_id)} · 第 {p.id} 条
                  </div>
                  <PendingUpdateItem pending={p} />
                </div>
              ))}
            </div>
          )}
        </div>
      }
    />
  );
}
