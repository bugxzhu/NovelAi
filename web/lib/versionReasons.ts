import type { ChapterVersionReason } from "./types";

export const VERSION_REASONS: Record<ChapterVersionReason, { icon: string; label: string }> = {
  manual: { icon: "💾", label: "手动" },
  pre_ai_accept: { icon: "🤖", label: "AI 生成前" },
  pre_polish_accept: { icon: "✨", label: "润色前" },
  pre_finalize: { icon: "✓", label: "定稿前" },
  pre_restore: { icon: "⏪", label: "恢复前" },
};

export const FALLBACK_REASON = { icon: "📄", label: "未知" };

export function formatReason(reason: string): { icon: string; label: string } {
  return (reason as ChapterVersionReason) in VERSION_REASONS
    ? VERSION_REASONS[reason as ChapterVersionReason]
    : FALLBACK_REASON;
}
