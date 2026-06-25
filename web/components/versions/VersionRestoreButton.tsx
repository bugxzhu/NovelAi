"use client";

import { useRouter } from "next/navigation";
import { useRestoreChapterVersion } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";

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
  // NOTE: useRestoreChapterVersion takes (versionId, chapterId) — Task 3 fixed this signature
  const restore = useRestoreChapterVersion(versionId ?? 0, chapterId);

  if (versionId === null) return null;

  const handleRestore = async () => {
    if (!confirm("确认恢复？当前内容会自动存为版本，可再次撤回。")) return;
    try {
      const result = await restore.mutateAsync();
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
