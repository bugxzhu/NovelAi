"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useRestoreChapterVersion } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";
import type { Chapter, ChapterVersionRestoreResponse } from "@/lib/types";

export function VersionRestoreButton({
  versionId,
  chapterId,
  projectId,
}: {
  versionId: number | null;
  chapterId: number;
  projectId: number;
}) {
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  // NOTE: useRestoreChapterVersion takes (versionId, chapterId) — Task 3 fixed this signature
  const restore = useRestoreChapterVersion(versionId ?? 0, chapterId);

  if (versionId === null) return null;

  const handleRestore = async () => {
    if (!confirm("确认恢复？当前内容会自动存为版本，可再次撤回。")) return;
    try {
      const result: ChapterVersionRestoreResponse = await restore.mutateAsync();
      // Seed the React Query cache with the restored content so the editor
      // page (which mounts a fresh TipTap instance on a separate route) reads
      // the new content synchronously on mount. ChapterEditor's sync useEffect
      // only depends on chapter.id, so without this the stale cached content
      // would win the race against the background refetch triggered by
      // useRestoreChapterVersion's invalidateQueries.
      const cached = qc.getQueryData<Chapter>(["chapter", chapterId]);
      if (cached) {
        qc.setQueryData<Chapter>(["chapter", chapterId], {
          ...cached,
          content: result.restored_content,
          char_count: result.new_char_count,
          updated_at: new Date().toISOString(),
        });
      }
      toast(`已恢复，原内容已存为 ⏪ 版本 #${result.new_pre_restore_id}`, "success");
      router.push(`/projects/${projectId}/chapters/${chapterId}`);
    } catch (e) {
      toast(`恢复失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <button
      type="button"
      onClick={handleRestore}
      disabled={restore.isPending}
      className="px-3 py-1.5 rounded bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-50"
    >
      {restore.isPending ? "恢复中..." : "⏩ 恢复此版本"}
    </button>
  );
}
