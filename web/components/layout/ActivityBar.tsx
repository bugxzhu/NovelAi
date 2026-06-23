"use client";

import { usePathname, useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { SettingsButton } from "@/components/layout/SettingsButton";
import { usePendingCount } from "@/lib/queries";

const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters", view: "chapters" as const },
  { icon: "👥", label: "人物", path: "characters", view: "characters" as const },
  { icon: "🤝", label: "关系", path: "relationships", view: "relationships" as const },
  { icon: "🎯", label: "事件", path: "events", view: "events" as const },
  { icon: "📊", label: "情节线", path: "plot-lines", view: "plot-lines" as const },
  { icon: "🗺️", label: "蓝图", path: "outline", view: "outline" as const },
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
  { icon: "📜", label: "历史", path: "history", view: "history" as const },
  { icon: "📋", label: "待处理", path: "pending", view: "pending" as const },
  { icon: "🔍", label: "搜索", path: "search", view: "search" as const },
];

export function ActivityBar({ projectId }: { projectId: number }) {
  const pathname = usePathname();
  const router = useRouter();
  const base = `/projects/${projectId}`;
  const isHome = pathname === "/";
  const { data: pendingCount } = usePendingCount(projectId);
  return (
    <aside className="w-10 bg-sidebar flex flex-col items-center py-2 gap-1 shrink-0">
      <button
        onClick={() => router.push("/")}
        title="返回项目列表"
        className={`w-8 h-8 flex flex-col items-center justify-center rounded ${
          isHome
            ? "bg-accent-strong text-white"
            : "hover:bg-hover-strong text-text-muted"
        }`}
      >
        <span className="text-base leading-none">🏠</span>
      </button>
      <div className="w-6 h-px bg-line my-1" />
      {ITEMS.map((it) => {
        const isActive = pathname.startsWith(`${base}/${it.path}`);
        return (
          <button
            key={it.path}
            onClick={() => router.push(`${base}/${it.path}`)}
            title={it.label}
            className={`relative w-8 h-8 flex flex-col items-center justify-center rounded ${
              isActive
                ? "bg-accent-strong text-white"
                : "hover:bg-hover-strong text-text-muted"
            }`}
          >
            <span className="text-base leading-none">{it.icon}</span>
            {it.path === "pending" && pendingCount && pendingCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 bg-red-600 text-white text-[9px] px-1 rounded-full leading-tight min-w-[14px] text-center">
                {pendingCount > 99 ? "99+" : pendingCount}
              </span>
            )}
          </button>
        );
      })}
      <div className="flex-1" />
      <SettingsButton />
      <ThemeToggle />
    </aside>
  );
}
