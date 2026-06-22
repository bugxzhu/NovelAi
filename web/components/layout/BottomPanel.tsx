"use client";

import { useState } from "react";
import { useChapter } from "@/lib/queries";
import { useUIStore } from "@/lib/store";
import { GenerateForm } from "@/components/generation/GenerateForm";
import { StreamView } from "@/components/generation/StreamView";

export function BottomPanel({ chapterId }: { chapterId: number }) {
  const { bottomPanelOpen, toggleBottomPanel } = useUIStore();
  const { data: chapter } = useChapter(chapterId);
  const [outlineExpanded, setOutlineExpanded] = useState(true);

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

  const outline = chapter?.outline ?? "";

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
          {/* 大纲显示区 */}
          {outline && (
            <div className="mb-3">
              <button
                onClick={() => setOutlineExpanded(!outlineExpanded)}
                className="text-xs text-text-muted-bright mb-1"
              >
                {outlineExpanded ? "▼" : "▶"} 大纲
              </button>
              {outlineExpanded && (
                <pre className="text-xs text-text-muted bg-input/50 rounded p-2 whitespace-pre-wrap">
                  {outline}
                </pre>
              )}
            </div>
          )}
          <GenerateForm chapterId={chapterId} />
        </div>
        <div className="flex-1 overflow-hidden">
          <StreamView chapterId={chapterId} />
        </div>
      </div>
    </div>
  );
}
