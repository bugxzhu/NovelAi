"use client";

import { useEffect, useRef } from "react";
import type { Editor } from "@tiptap/react";
import { useReviewStore } from "@/lib/store";
import { useToast } from "@/components/ui/Toast";
import { Button } from "@/components/ui/Button";
import type { Category, Issue, Severity } from "@/lib/types";

const CATEGORY_LABEL: Record<Category, string> = {
  character: "人物一致性",
  relationship: "关系合理性",
  plot: "情节矛盾",
  foreshadow: "伏笔完整性",
  worldview: "世界观一致性",
};

const CATEGORY_ORDER: Category[] = [
  "character", "relationship", "plot", "foreshadow", "worldview",
];

const SEVERITY_ICON: Record<Severity, string> = {
  error: "🔴",
  warn: "🟡",
  info: "🔵",
};

export function ReviewModal({
  chapterId,
  editor,
}: {
  chapterId: number;
  editor: Editor | null;
}) {
  const issues = useReviewStore((s) => s.issuesByChapter[chapterId] || []);
  const isOpen = useReviewStore((s) => s.modalOpenFor === chapterId);
  const close = useReviewStore((s) => s.closeModal);
  const toast = useToast();
  const editorRef = useRef(editor);
  editorRef.current = editor;

  // Apply highlights when issues change
  useEffect(() => {
    const ed = editorRef.current;
    if (!ed) return;

    ed.commands.unsetAllIssueHighlights();

    if (!issues.length) return;

    const fullText = ed.getText();
    issues.forEach((issue, idx) => {
      if (!issue.location) return;
      const idxInText = fullText.indexOf(issue.location);
      if (idxInText < 0) return;  // graceful degrade
      // NOTE: text offset → ProseMirror pos conversion is approximate.
      // TipTap's getText() concatenates block nodes with newlines; the resulting
      // offset is close to but not exactly the ProseMirror document position.
      // For simple paragraph-based chapters this works well; complex block
      // structures (lists, blockquotes) may shift by a few positions.
      const from = idxInText + 1;  // ProseMirror is 1-indexed
      const to = from + issue.location.length;
      try {
        ed.commands.setIssueHighlight(
          { issueId: `${idx}`, severity: issue.severity },
          from, to,
        );
      } catch {
        // Position out of range; skip silently (graceful degrade)
      }
    });
  }, [issues]);

  if (!isOpen) return null;

  const byCategory = new Map<Category, Issue[]>();
  for (const cat of CATEGORY_ORDER) {
    const items = issues.filter((i) => i.category === cat);
    if (items.length) byCategory.set(cat, items);
  }

  const errorCount = issues.filter((i) => i.severity === "error").length;
  const warnCount = issues.filter((i) => i.severity === "warn").length;
  const infoCount = issues.filter((i) => i.severity === "info").length;

  const handleIssueClick = (issueId: string) => {
    const ed = editorRef.current;
    if (!ed) return;
    let foundPos: number | null = null;
    ed.state.doc.descendants((node: any, pos: number) => {
      if (foundPos !== null) return false;
      const mark = node.marks.find((m: any) =>
        m.type.name === "issueHighlight" && m.attrs.issueId === issueId
      );
      if (mark) {
        foundPos = pos;
        return false;
      }
      return true;
    });
    if (foundPos !== null) {
      ed.commands.setTextSelection(foundPos);
      ed.commands.scrollIntoView();
    }
  };

  const handleCopyAll = () => {
    const text = issues.map((i) =>
      `[${SEVERITY_ICON[i.severity]} ${CATEGORY_LABEL[i.category]}]\n` +
      (i.location ? `位置：${i.location}\n` : "") +
      `问题：${i.description}\n` +
      (i.suggestion ? `建议：${i.suggestion}\n` : "")
    ).join("\n");
    navigator.clipboard.writeText(text).then(
      () => toast("已复制到剪贴板", "success"),
      () => toast("复制失败", "error"),
    );
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-panel border border-line rounded max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-line">
          <h2 className="text-lg">审稿报告</h2>
          <button onClick={close} className="text-text-muted hover:text-text">×</button>
        </div>

        <div className="p-4">
          {issues.length === 0 ? (
            <p className="text-text-muted">✓ 未发现问题</p>
          ) : (
            <>
              <div className="text-sm text-text-muted mb-4">
                共 {issues.length} 条 Issue：🔴 {errorCount} · 🟡 {warnCount} · 🔵 {infoCount}
              </div>
              {Array.from(byCategory.entries()).map(([cat, items]) => (
                <div key={cat} className="mb-4">
                  <h3 className="text-sm text-text-muted-bright mb-2">
                    ▼ {CATEGORY_LABEL[cat]}（{items.length}）
                  </h3>
                  <div className="space-y-2 pl-4">
                    {items.map((issue, idx) => {
                      const issueIdx = issues.indexOf(issue);
                      return (
                        <div
                          key={`${cat}-${idx}`}
                          onClick={() => handleIssueClick(`${issueIdx}`)}
                          className="border border-line rounded p-2 cursor-pointer hover:bg-hover"
                        >
                          <div className="flex items-start gap-2">
                            <span>{SEVERITY_ICON[issue.severity]}</span>
                            <div className="flex-1">
                              <div className="text-sm text-text">
                                {issue.description}
                              </div>
                              {issue.location && (
                                <div className="text-xs text-text-dim mt-1">
                                  位置：&quot;{issue.location}&quot;
                                </div>
                              )}
                              {issue.suggestion && (
                                <div className="text-xs text-text-muted mt-1">
                                  建议：{issue.suggestion}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-line">
          <Button variant="ghost" onClick={handleCopyAll}>📋 复制全部</Button>
          <Button variant="primary" onClick={close}>✓ 我知道了</Button>
        </div>
      </div>
    </div>
  );
}
