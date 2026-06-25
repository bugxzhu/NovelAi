"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getCurrentChapterContent } from "@/lib/editor";
import { useCreateChapterVersion } from "@/lib/queries";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";

export function FinalizeButton({
  chapterId,
  isFinal,
}: {
  chapterId: number;
  isFinal: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const createVersion = useCreateChapterVersion(chapterId);
  const [finalizing, setFinalizing] = useState(false);

  const handleFinalize = async () => {
    setFinalizing(true);
    try {
      try {
        const content = getCurrentChapterContent();
        await createVersion.mutateAsync({ content, reason: "pre_finalize" });
      } catch {
        // Non-blocking: snapshot failure shouldn't break the primary action
      }
      const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8005";
      const r = await fetch(`${base}/api/chapters/${chapterId}/finalize`, {
        method: "POST",
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        const reason =
          (err.detail && (err.detail.reason || err.detail.raw)) ||
          (typeof err.detail === "string" ? err.detail : `HTTP ${r.status}`);
        throw new Error(reason);
      }
      const data = await r.json();
      toast(`已抽取 ${data.pending_created} 条新事实，摘要已生成`, "success");
      qc.invalidateQueries({ queryKey: ["chapter", chapterId] });
      qc.invalidateQueries({ queryKey: ["chapters"] });
      qc.invalidateQueries({ queryKey: ["pending-updates"] });
      qc.invalidateQueries({ queryKey: ["pending-count"] });
    } catch (e) {
      toast(`抽取失败: ${(e as Error).message}`, "error");
    } finally {
      setFinalizing(false);
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleFinalize}
      disabled={finalizing}
    >
      {finalizing
        ? "⏳ 抽取中..."
        : isFinal
        ? "↻ 重新抽取"
        : "✓ 完成本章"}
    </Button>
  );
}
