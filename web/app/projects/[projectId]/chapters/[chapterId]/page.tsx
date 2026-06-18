"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useChapter, useChapters, useCreateChapter } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterItem } from "@/components/entities/ChapterItem";
import { ChapterEditor } from "@/components/editor/ChapterEditor";
import { ContextPanel } from "@/components/layout/ContextPanel";
import { BottomPanel } from "@/components/layout/BottomPanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { Button } from "@/components/ui/Button";

export default function ChapterPage() {
  const { projectId, chapterId } = useParams<{ projectId: string; chapterId: string }>();
  const pid = Number(projectId);
  const cid = Number(chapterId);
  const { data: chapter, isLoading } = useChapter(cid);
  const { data: chapters } = useChapters(pid);
  const createChapter = useCreateChapter();
  const hydrate = useGenerateParams((s) => s.hydrateFromChapter);

  // Hydrate generate params from chapter defaults once per chapter entry
  useEffect(() => {
    if (chapter) hydrate(chapter);
  }, [chapter?.id, hydrate]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading || !chapter) {
    return <div className="flex-1 p-8 text-[#888]">加载章节...</div>;
  }

  const handleCreate = async () => {
    const order = (chapters?.reduce((m, c) => Math.max(m, c.order_index), 0) ?? 0) + 1;
    const ch = await createChapter.mutateAsync({
      project_id: pid,
      order_index: order,
      title: `第 ${order} 章`,
    });
    window.location.href = `/projects/${pid}/chapters/${ch.id}`;
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="章节"
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChapter.isPending}>
              + 新建
            </Button>
          }
        >
          {(chapters ?? [])
            .slice()
            .sort((a, b) => a.order_index - b.order_index)
            .map((c) => (
              <ChapterItem
                key={c.id}
                chapter={c}
                href={`/projects/${pid}/chapters/${c.id}`}
                active={c.id === cid}
              />
            ))}
        </SidePanel>
      }
      editor={<ChapterEditor chapter={chapter} />}
      contextPanel={<ContextPanel projectId={pid} />}
      bottomPanel={<BottomPanel chapterId={cid} />}
    />
  );
}
