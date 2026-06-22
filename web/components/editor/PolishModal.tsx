"use client";

import { useRef } from "react";
import type { Editor } from "@tiptap/react";
import { usePolishStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";

export function PolishModal({ editor }: { editor: Editor | null }) {
  const result = usePolishStore((s) => s.result);
  const isOpen = usePolishStore((s) => s.modalOpen);
  const selectedText = usePolishStore((s) => s.selectedText);
  const selectionFrom = usePolishStore((s) => s.selectionFrom);
  const selectionTo = usePolishStore((s) => s.selectionTo);
  const close = usePolishStore((s) => s.closeModal);
  const toast = useToast();
  // Keep a ref to the editor so the accept handler always sees the latest
  // instance even if the prop updates between renders.
  const editorRef = useRef(editor);
  editorRef.current = editor;

  if (!isOpen || !result) return null;

  const handleAccept = () => {
    const ed = editorRef.current;
    if (!ed) {
      toast("编辑器未就绪", "error");
      return;
    }
    if (
      result.is_selection &&
      selectionFrom != null &&
      selectionTo != null
    ) {
      // Replace the captured selection range with the polished text.
      ed.chain()
        .focus()
        .setTextSelection({ from: selectionFrom, to: selectionTo })
        .deleteSelection()
        .insertContent(result.polished_text)
        .run();
    } else {
      // Replace the whole chapter.
      ed.commands.setContent(result.polished_text);
    }
    toast("已应用润色", "success");
    close();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-panel border border-line rounded max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">
            ✨ 润色结果
            {result.is_selection ? "（选中段落）" : "（整章）"}
          </h2>
          <button
            onClick={close}
            className="text-text-muted hover:text-text"
          >
            ×
          </button>
        </div>

        <div className="p-4">
          {selectedText && (
            <div className="mb-3">
              <div className="text-xs text-text-muted-bright mb-1">
                📝 原文（选中段落）：
              </div>
              <div className="text-xs text-text-dim bg-input/30 rounded p-2 line-clamp-3 whitespace-pre-wrap">
                {selectedText}
              </div>
            </div>
          )}
          <div>
            <div className="text-xs text-text-muted-bright mb-1">✨ 润色后：</div>
            <div className="text-sm text-text bg-input/30 rounded p-3 whitespace-pre-wrap max-h-[50vh] overflow-y-auto">
              {result.polished_text}
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-line">
          <Button variant="ghost" onClick={close}>✗ 不用了</Button>
          <Button variant="primary" onClick={handleAccept}>
            ✓ 接受润色
          </Button>
        </div>
      </div>
    </div>
  );
}
