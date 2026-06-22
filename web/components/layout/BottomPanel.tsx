"use client";

import { useEffect, useState } from "react";
import { useChapter, useUpdateChapter } from "@/lib/queries";
import { useUIStore } from "@/lib/store";
import { GenerateForm } from "@/components/generation/GenerateForm";
import { StreamView } from "@/components/generation/StreamView";

export function BottomPanel({ chapterId }: { chapterId: number }) {
  const { bottomPanelOpen, toggleBottomPanel } = useUIStore();
  const { data: chapter } = useChapter(chapterId);
  const updateChapter = useUpdateChapter(chapterId, chapter?.project_id ?? 0);
  const [outlineExpanded, setOutlineExpanded] = useState(true);
  const [outlineDraft, setOutlineDraft] = useState("");

  // Sync draft when chapter changes
  useEffect(() => {
    setOutlineDraft(chapter?.outline ?? "");
  }, [chapter?.id, chapter?.outline]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced autosave
  useEffect(() => {
    if (outlineDraft === (chapter?.outline ?? "")) return;
    const timer = setTimeout(() => {
      updateChapter.mutate({ outline: outlineDraft });
    }, 1000);
    return () => clearTimeout(timer);
  }, [outlineDraft]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!bottomPanelOpen) {
    return (
      <button
        onClick={toggleBottomPanel}
        className="w-full h-full flex items-center justify-center text-xs text-text-muted hover:text-text"
      >
        ⚡ 生成（展开）
      </button>
    );
  }

  const hasOutline = outlineDraft.trim().length > 0;

  const handleClear = () => {
    setOutlineDraft("");
    updateChapter.mutate({ outline: "" });
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-1 bg-input border-b border-line">
        <span className="text-xs text-text-muted">⚡ 生成</span>
        <button
          onClick={toggleBottomPanel}
          className="text-xs text-text-muted hover:text-white"
        >
          ▾ 收起
        </button>
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-2/5 overflow-y-auto p-3 border-r border-line">
          {/* 大纲编辑区 */}
          <div className="mb-3">
            <div className="flex items-center justify-between mb-1">
              <button
                onClick={() => setOutlineExpanded(!outlineExpanded)}
                className="text-xs text-text-muted-bright"
              >
                {outlineExpanded ? "▼" : "▶"} 大纲
              </button>
              {hasOutline && (
                <button
                  onClick={handleClear}
                  className="text-xs text-text-dim hover:text-red-400"
                >
                  清空
                </button>
              )}
            </div>
            {outlineExpanded && (
              <textarea
                value={outlineDraft}
                onChange={(e) => setOutlineDraft(e.target.value)}
                placeholder="章节大纲（可从探讨选用分支，或直接编辑）"
                rows={hasOutline ? 4 : 2}
                className="w-full text-xs text-text-muted bg-input/50 border border-line rounded p-2 resize-y"
              />
            )}
          </div>
          <GenerateForm chapterId={chapterId} />
        </div>
        <div className="flex-1 overflow-hidden">
          <StreamView chapterId={chapterId} />
        </div>
      </div>
    </div>
  );
}
