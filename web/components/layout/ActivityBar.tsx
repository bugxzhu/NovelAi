"use client";

import { usePathname, useRouter } from "next/navigation";

const ITEMS = [
  { icon: "📚", label: "章节", path: "chapters", view: "chapters" as const },
  { icon: "👥", label: "人物", path: "characters", view: "characters" as const },
  { icon: "🌍", label: "设定", path: "lore", view: "lore" as const },
  { icon: "📜", label: "历史", path: "history", view: "history" as const },
  { icon: "🔍", label: "搜索", path: "search", view: "search" as const },
];

export function ActivityBar({ projectId }: { projectId: number }) {
  const pathname = usePathname();
  const router = useRouter();
  const base = `/projects/${projectId}`;
  return (
    <aside className="w-10 bg-[#333] flex flex-col items-center py-2 gap-1 shrink-0">
      {ITEMS.map((it) => {
        const isActive = pathname.startsWith(`${base}/${it.path}`);
        return (
          <button
            key={it.path}
            onClick={() => router.push(`${base}/${it.path}`)}
            title={it.label}
            className={`w-8 h-8 flex flex-col items-center justify-center rounded ${
              isActive
                ? "bg-[#094771] text-white"
                : "hover:bg-[#3a3a3a] text-[#888]"
            }`}
          >
            <span className="text-base leading-none">{it.icon}</span>
          </button>
        );
      })}
    </aside>
  );
}
