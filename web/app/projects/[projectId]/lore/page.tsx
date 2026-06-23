"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useLore, useCreateLore, useWorldOverview } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { LoreForm } from "@/components/entities/LoreForm";
import { WorldOverviewForm } from "@/components/entities/WorldOverviewForm";
import { Button } from "@/components/ui/Button";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import type { LoreType } from "@/lib/types";

const TABS: Array<{ key: string; label: string; types: LoreType[] }> = [
  { key: "overview", label: "世界观", types: [] },
  { key: "location", label: "地点", types: ["location"] },
  { key: "faction", label: "势力", types: ["faction"] },
  { key: "item", label: "物品", types: ["item"] },
  { key: "other", label: "其他", types: ["organization", "concept", "custom"] },
];

export default function LorePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [tab, setTab] = useState<string>("location");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { data: lore } = useLore(pid);
  const createLore = useCreateLore();
  const { data: worldOverview } = useWorldOverview(pid);

  const currentTab = TABS.find((t) => t.key === tab)!;
  const filtered = (lore ?? []).filter((l) =>
    tab === "overview" ? false : currentTab.types.includes(l.type)
  );
  const selected = (lore ?? []).find((l) => l.id === selectedId);

  const handleCreate = async () => {
    if (tab === "overview") return;
    const l = await createLore.mutateAsync({
      project_id: pid,
      type: currentTab.types[0],
      name: "未命名",
    });
    setSelectedId(l.id);
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="设定">
          <div className="flex flex-wrap gap-1 mb-2 px-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setTab(t.key);
                  setSelectedId(null);
                }}
                className={`px-2 py-0.5 rounded text-xs ${
                  tab === t.key
                    ? "bg-accent text-white"
                    : "bg-button text-text"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {tab !== "overview" && (
            <div className="px-1 mb-2">
              <Button variant="ghost" onClick={handleCreate} disabled={createLore.isPending}>
                + 新建
              </Button>
            </div>
          )}
          {tab === "overview" ? (
            <p className="text-xs text-text-muted p-2">
              {worldOverview ? "点右侧编辑" : "右侧创建"}
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-xs text-text-muted p-2">
              还没有设定。点击&quot;+ 新建&quot;添加地点、势力、物品等，让 AI 的世界更丰富。
            </p>
          ) : (
            filtered.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelectedId(l.id)}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === l.id
                    ? "bg-active text-white"
                    : "hover:bg-hover text-text"
                }`}
              >
                {l.name}
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          {tab === "overview" ? (
            <WorldOverviewForm projectId={pid} />
          ) : (
            <LoreForm
              projectId={pid}
              lore={selected}
              onDeleted={() => setSelectedId(null)}
            />
          )}
        </div>
      }
    />
  );
}
