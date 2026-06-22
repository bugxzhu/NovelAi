"use client";

import { useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import { api, ApiError } from "@/lib/api";
import { usePolishStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";

// Two-state modal (mirrors DiscussModal's pattern):
// 1. Input state (no result yet): direction textarea + "开始润色 →" button.
//    Shows the captured selection preview if the user had text selected.
// 2. Result state (result available): polished version cards — 2 for selection
//    mode, 1 for whole-chapter mode. Each card has its own "采用此版本" button
//    that replaces the captured range (selection) or whole content (chapter)
//    with that specific version.
//
// Accept logic: the captured ProseMirror positions (polishSelectionFrom/To) are
// used to replace exactly that slice; whole-chapter accept calls setContent.
// An editor ref guards against prop updates between renders.
export function PolishModal({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  const polishResult = usePolishStore((s) => s.polishResult);
  const polishModalOpen = usePolishStore((s) => s.polishModalOpen);
  const polishSelectedText = usePolishStore((s) => s.polishSelectedText);
  const polishSelectionFrom = usePolishStore((s) => s.polishSelectionFrom);
  const polishSelectionTo = usePolishStore((s) => s.polishSelectionTo);
  const setPolishResult = usePolishStore((s) => s.setPolishResult);
  const closePolishModal = usePolishStore((s) => s.closePolishModal);
  const toast = useToast();
  const [direction, setDirection] = useState("");
  const [loading, setLoading] = useState(false);

  const editorRef = useRef(editor);
  editorRef.current = editor;

  if (!polishModalOpen) return null;

  const isSelection = polishSelectedText.trim().length > 0;

  const handlePolish = async () => {
    setLoading(true);
    try {
      const r = await api.polishChapter(
        chapterId,
        isSelection ? polishSelectedText : undefined,
        direction || undefined,
      );
      setPolishResult(r);
      toast("润色完成", "success");
    } catch (e) {
      const msg = e instanceof ApiError
        ? `${e.status}: ${JSON.stringify(e.body)}`
        : (e as Error).message;
      toast(`润色失败: ${msg}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleAccept = (text: string) => {
    const ed = editorRef.current;
    if (!ed) {
      toast("编辑器未就绪", "error");
      return;
    }
    if (
      isSelection &&
      polishSelectionFrom != null &&
      polishSelectionTo != null
    ) {
      ed.chain()
        .focus()
        .setTextSelection({ from: polishSelectionFrom, to: polishSelectionTo })
        .deleteSelection()
        .insertContent(text)
        .run();
    } else {
      ed.commands.setContent(text);
    }
    toast("已应用润色", "success");
    closePolishModal();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-panel border border-line rounded max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">
            ✨ 润色{isSelection ? "（选中段落）" : "（整章）"}
          </h2>
          <button
            onClick={closePolishModal}
            className="text-text-muted hover:text-text"
          >
            ×
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Selected text context */}
          {isSelection && (
            <div className="bg-input/50 border border-line rounded p-2">
              <div className="text-xs text-text-muted-bright mb-1">
                📝 选中段落：
              </div>
              <div className="text-xs text-text-muted line-clamp-3">
                {polishSelectedText}
              </div>
            </div>
          )}

          {/* Direction input */}
          <div>
            <label className="text-xs text-text-muted-bright block mb-1">
              润色方向（可选）
            </label>
            <textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              placeholder="如：增加心理描写 / 让节奏更紧凑 / 更有画面感..."
              rows={2}
              className="w-full bg-input border border-line rounded p-2 text-text text-sm"
            />
          </div>

          {/* Action button (only in input phase) */}
          {!polishResult && (
            <div className="flex justify-end">
              <Button
                variant="primary"
                onClick={handlePolish}
                disabled={loading}
              >
                {loading ? "⏳ 润色中..." : "开始润色 →"}
              </Button>
            </div>
          )}

          {/* Results */}
          {polishResult && (
            <div className="space-y-3">
              <div className="text-xs text-text-muted">
                {polishResult.polished_texts.length > 1
                  ? `${polishResult.polished_texts.length} 个版本，选择一个采用：`
                  : "润色结果："}
              </div>
              {polishResult.polished_texts.map((text, idx) => (
                <div key={idx} className="border border-line rounded p-3">
                  {polishResult.polished_texts.length > 1 && (
                    <div className="text-xs text-text-muted-bright mb-2">
                      方案 {String.fromCharCode(65 + idx)}
                    </div>
                  )}
                  <div className="text-sm text-text whitespace-pre-wrap max-h-[40vh] overflow-y-auto">
                    {text}
                  </div>
                  <div className="mt-2 flex justify-end">
                    <Button
                      variant="primary"
                      onClick={() => handleAccept(text)}
                    >
                      ✓ 采用此版本
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-line">
          <Button variant="ghost" onClick={closePolishModal}>
            {polishResult ? "✗ 都不用" : "取消"}
          </Button>
        </div>
      </div>
    </div>
  );
}
