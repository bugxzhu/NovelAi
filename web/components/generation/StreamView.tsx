"use client";

import { useGenerate } from "./useGenerate";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { Editor } from "@tiptap/react";

export function StreamView({ chapterId }: { chapterId: number }) {
  const { events, generatedText, status, reset, retry, error } = useGenerate(chapterId);
  const toast = useToast();

  const meta = events.find((e) => e.type === "meta");
  const contextEvent = events.find((e) => e.type === "context");
  const doneEvent = events.find((e) => e.type === "done");

  const handleAccept = () => {
    const editor = (window as unknown as { __chapterEditor?: Editor }).__chapterEditor;
    if (!editor) {
      toast("编辑器尚未就绪，请稍候再试", "error");
      return;
    }
    if (!generatedText) return;
    editor.chain().focus().insertContent(generatedText).run();
    // Trigger immediate save by simulating blur — ChapterEditor's onBlur handler
    // reads the freshest markdown from the editor itself, so we don't need to compute it here.
    editor.commands.blur();
    reset();
  };

  if (events.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-[#888]">
        {status === "preparing"
          ? "正在组装上下文…"
          : "暂无生成。点左侧 ✨ 生成 开始。"}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3 text-xs">
      {meta && meta.type === "meta" && (
        <div className="text-[#888]">
          <span className="text-[#aaa]">[meta]</span> log_id={meta.generation_log_id} · model={meta.model}
        </div>
      )}

      {contextEvent && contextEvent.type === "context" && (
        <details className="bg-[#1e1e1e] rounded p-2">
          <summary className="cursor-pointer text-[#888]">
            📋 常驻层预览（{contextEvent.context_bundle.characters.length} 人物 ·{" "}
            {contextEvent.context_bundle.location_lore.length} 地点）
          </summary>
          <pre className="mt-2 text-[10px] text-[#aaa] whitespace-pre-wrap">
            {JSON.stringify(contextEvent.context_bundle, null, 2)}
          </pre>
        </details>
      )}

      <div className="font-serif text-sm leading-relaxed whitespace-pre-wrap min-h-[120px] text-[#cccccc]">
        {generatedText}
        {(status === "streaming" || status === "preparing") && (
          <span className="inline-block w-2 h-4 bg-[#888] animate-pulse ml-0.5" />
        )}
      </div>

      {error && (
        <div className="p-2 bg-red-950/30 border border-red-900 rounded text-red-400">
          ✗ {error}
        </div>
      )}

      {doneEvent && doneEvent.type === "done" && (
        <div className="flex items-center justify-between pt-2 border-t border-[#3c3c3c]">
          <span className="text-[#888]">
            ✓ 完成 · 输入 {doneEvent.input_tokens} / 输出 {doneEvent.output_tokens} tokens
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={retry}>
              重试
            </Button>
            <Button variant="primary" onClick={handleAccept} disabled={!generatedText}>
              ✓ 接受并插入
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
