"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { useReviewStore } from "@/lib/store";
import { Button } from "@/components/ui/Button";

export function ReviewButton({ chapterId }: { chapterId: number }) {
  const toast = useToast();
  const setIssues = useReviewStore((s) => s.setIssues);
  const [state, setState] = useState<"idle" | "reviewing">("idle");

  const handleReview = async () => {
    setState("reviewing");
    try {
      const r = await api.reviewChapter(chapterId);
      setIssues(chapterId, r.issues);
      toast(`审稿完成：${r.issues.length} 条 Issue`, "success");
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${JSON.stringify(e.body)}`
        : (e as Error).message;
      toast(`审稿失败: ${msg}`, "error");
    } finally {
      setState("idle");
    }
  };

  return (
    <Button
      variant="primary"
      onClick={handleReview}
      disabled={state === "reviewing"}
    >
      {state === "reviewing" ? "⏳ 审稿中..." : "🔍 审稿"}
    </Button>
  );
}
