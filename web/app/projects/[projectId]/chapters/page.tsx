"use client";

import { useParams } from "next/navigation";
import { useChapters, useCreateChapter } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterItem } from "@/components/entities/ChapterItem";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";

export default function ChaptersListPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: chapters, isLoading } = useChapters(pid);
  const createChapter = useCreateChapter();

  const handleCreate = async () => {
    const order = (chapters?.reduce((m, c) => Math.max(m, c.order_index), 0) ?? 0) + 1;
    const ch = await createChapter.mutateAsync({
      project_id: pid,
      order_index: order,
      title: `第 ${order} 章`,
    });
    window.location.href = `/projects/${pid}/chapters/${ch.id}`;
  };

  // Chinese word count: strip whitespace, count remaining characters (CJK + latin).
  // content is Markdown; whitespace includes spaces/tabs/newlines, which we don't
  // want to inflate the count.
  const totalChars = (chapters ?? []).reduce((sum, ch) => {
    return sum + (ch.content || "").replace(/\s/g, "").length;
  }, 0);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title={`章节 · 共 ${chapters?.length ?? 0} 章 · ${totalChars} 字`}
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChapter.isPending}>
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : !chapters || chapters.length === 0 ? (
            <p className="text-xs text-text-muted p-2">还没有章节</p>
          ) : (
            chapters
              .slice()
              .sort((a, b) => a.order_index - b.order_index)
              .map((c) => (
                <ChapterItem
                  key={c.id}
                  chapter={c}
                  href={`/projects/${pid}/chapters/${c.id}`}
                  active={false}
                />
              ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full flex items-center justify-center text-text-muted">
          请从左侧选择一个章节
        </div>
      }
    />
  );
}
