"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import {
  useGenerationLogsByProject,
  useGenerationLog,
  useChapters,
} from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";

export default function HistoryPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: logs, isLoading } = useGenerationLogsByProject(pid);
  const { data: chapters } = useChapters(pid);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: detail } = useGenerationLog(selectedId ?? 0);

  // Group logs by chapter_id, ordered by chapter order_index
  const grouped = useMemo(() => {
    const chapterOrder = new Map(
      (chapters ?? []).map((c) => [c.id, c.order_index])
    );
    const groups = new Map<number, NonNullable<typeof logs>>();
    for (const log of logs ?? []) {
      const arr = groups.get(log.chapter_id) ?? [];
      arr.push(log);
      groups.set(log.chapter_id, arr);
    }
    return Array.from(groups.entries())
      .map(([chapterId, items]) => ({ chapterId, items: items! }))
      .sort(
        (a, b) =>
          (chapterOrder.get(b.chapterId) ?? 0) -
          (chapterOrder.get(a.chapterId) ?? 0)
      );
  }, [logs, chapters]);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="历史">
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : grouped.length === 0 ? (
            <p className="text-xs text-text-muted p-2">无生成记录</p>
          ) : (
            grouped.map(({ chapterId, items }) => {
              const ch = (chapters ?? []).find((c) => c.id === chapterId);
              return (
                <div key={chapterId} className="mb-2">
                  <div className="text-xs text-text-muted px-2 py-1">
                    {ch?.title ?? `Chapter ${chapterId}`} ({items.length})
                  </div>
                  {items.map((log) => (
                    <button
                      key={log.id}
                      onClick={() => setSelectedId(log.id)}
                      className={`block w-full text-left px-3 py-1.5 rounded text-xs ${
                        selectedId === log.id
                          ? "bg-active text-white"
                          : "hover:bg-hover text-text"
                      }`}
                    >
                      #{log.id} · {log.status} ·{" "}
                      {log.finished_at
                        ? new Date(log.finished_at).toLocaleString()
                        : "..."}
                    </button>
                  ))}
                </div>
              );
            })
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4 text-sm">
          {!detail ? (
            <p className="text-text-muted">请从左侧选择记录</p>
          ) : (
            <div className="space-y-4 max-w-3xl">
              <div className="text-xs text-text-muted">
                #{detail.id} · chapter_id={detail.chapter_id} · status={detail.status} ·{" "}
                input={detail.input_tokens} output={detail.output_tokens}
              </div>
              <details open>
                <summary className="cursor-pointer text-text-muted-bright">Beat + 指令</summary>
                <pre className="mt-2 p-2 bg-input rounded whitespace-pre-wrap text-xs">
                  {detail.beat_text}
                  {detail.instruction ? `\n\n[指令] ${detail.instruction}` : ""}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-text-muted-bright">System Prompt</summary>
                <pre className="mt-2 p-2 bg-input rounded whitespace-pre-wrap text-xs">
                  {detail.system_prompt}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-text-muted-bright">User Prompt</summary>
                <pre className="mt-2 p-2 bg-input rounded whitespace-pre-wrap text-xs">
                  {detail.user_prompt}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-text-muted-bright">Generated Text</summary>
                <pre className="mt-2 p-2 bg-input rounded whitespace-pre-wrap text-xs">
                  {detail.generated_text ?? "(empty)"}
                </pre>
              </details>
            </div>
          )}
        </div>
      }
    />
  );
}
