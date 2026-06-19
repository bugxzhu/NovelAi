"use client";

import { useUIStore } from "@/lib/store";
import { GenerateForm } from "@/components/generation/GenerateForm";
import { StreamView } from "@/components/generation/StreamView";

export function BottomPanel({ chapterId }: { chapterId: number }) {
  const { bottomPanelOpen, toggleBottomPanel } = useUIStore();

  if (!bottomPanelOpen) {
    return (
      <button
        onClick={toggleBottomPanel}
        className="w-full h-full flex items-center justify-center text-xs text-[#888] hover:text-[#cccccc]"
      >
        ⚡ 生成（展开）
      </button>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-1 bg-[#1e1e1e] border-b border-[#3c3c3c]">
        <span className="text-xs text-[#888]">⚡ 生成</span>
        <button
          onClick={toggleBottomPanel}
          className="text-xs text-[#888] hover:text-white"
        >
          ▾ 收起
        </button>
      </div>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-2/5 overflow-y-auto p-3 border-r border-[#3c3c3c]">
          <GenerateForm chapterId={chapterId} />
        </div>
        <div className="flex-1 overflow-hidden">
          <StreamView chapterId={chapterId} />
        </div>
      </div>
    </div>
  );
}
