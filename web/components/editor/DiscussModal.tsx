"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useDiscussStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import type { DiscussResponse } from "@/lib/types";

// Two-state modal:
// 1. Input state (no result yet): question textarea + "推演 →" button
// 2. Result state (result available): 3 branch cards + recommendation + reasoning
//
// Note on selector snapshot safety (mirrors ReviewModal pattern):
// `s.resultByChapter[chapterId] ?? null` returns either a stable DiscussResponse
// object (referentially equal across renders unless setResult fires) or the
// primitive `null` (also referentially stable). Unlike the array case in
// ReviewModal, no EMPTY constant is needed — `null` is not a fresh allocation.
export function DiscussModal({ chapterId }: { chapterId: number }) {
  const result = useDiscussStore((s) => s.resultByChapter[chapterId] ?? null);
  const isOpen = useDiscussStore((s) => s.modalOpenFor === chapterId);
  const close = useDiscussStore((s) => s.closeModal);
  const setResult = useDiscussStore((s) => s.setResult);
  const toast = useToast();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleDiscuss = async () => {
    if (!question.trim()) {
      toast("请输入你的设想", "error");
      return;
    }
    setLoading(true);
    try {
      const r = await api.discussChapter(chapterId, question);
      setResult(chapterId, r);
      toast("推演完成", "success");
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${JSON.stringify(e.body)}`
        : (e as Error).message;
      toast(`推演失败: ${msg}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleCopyAll = () => {
    if (!result) return;
    const text = `设想：${result.question}\n推荐：${result.recommended}\n理由：${result.reasoning}\n\n` +
      result.branches.map((b) =>
        `分支 ${b.label}：${b.title}\n  走向：${b.summary}\n  冲突：${b.conflicts}\n  机会：${b.opportunities}\n  人物：${b.character_impact}`
      ).join("\n\n");
    navigator.clipboard.writeText(text).then(
      () => toast("已复制", "success"),
      () => toast("复制失败", "error"),
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-panel border border-line rounded max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">💬 情节探讨</h2>
          <button onClick={close} className="text-text-muted hover:text-text">×</button>
        </div>

        <div className="p-4 space-y-4">
          {/* Question input (always visible at top) */}
          <div>
            <label className="text-xs text-text-muted-bright block mb-1">你的设想</label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="如果让李雷在这里和韩梅梅和解？"
              rows={2}
              className="w-full bg-input border border-line rounded p-2 text-text"
            />
            <div className="flex justify-end mt-2">
              <Button
                variant="primary"
                onClick={handleDiscuss}
                disabled={loading}
              >
                {loading ? "⏳ 推演中..." : "推演 →"}
              </Button>
            </div>
          </div>

          {/* Results */}
          {result && (
            <div className="border-t border-line pt-3">
              <div className="text-sm mb-2">
                ⭐ 推荐：分支 <strong>{result.recommended}</strong>
              </div>
              {result.reasoning && (
                <div className="text-xs text-text-muted mb-3">
                  理由：{result.reasoning}
                </div>
              )}

              <div className="space-y-3">
                {result.branches.map((branch) => {
                  const isRecommended = branch.label === result.recommended;
                  return (
                    <div
                      key={branch.label}
                      className={`border rounded p-3 ${
                        isRecommended
                          ? "border-accent bg-accent/10"
                          : "border-line"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-sm font-bold">
                          分支 {branch.label}：{branch.title}
                        </span>
                        {isRecommended && (
                          <span className="text-xs text-accent">✓ 推荐</span>
                        )}
                      </div>
                      <div className="text-xs space-y-1 pl-4">
                        <div><span className="text-text-muted-bright">走向：</span>{branch.summary}</div>
                        <div><span className="text-text-muted-bright">冲突：</span>{branch.conflicts}</div>
                        <div><span className="text-text-muted-bright">机会：</span>{branch.opportunities}</div>
                        <div><span className="text-text-muted-bright">人物：</span>{branch.character_impact}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-line">
          {result && (
            <Button variant="ghost" onClick={handleCopyAll}>📋 复制全部</Button>
          )}
          <Button variant="primary" onClick={close}>✓ 知道了</Button>
        </div>
      </div>
    </div>
  );
}
