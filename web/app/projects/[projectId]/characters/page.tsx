"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useCharacters, useCreateCharacter } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { CharacterForm } from "@/components/entities/CharacterForm";
import { Button } from "@/components/ui/Button";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";

export default function CharactersPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const { data: characters, isLoading } = useCharacters(pid);
  const createChar = useCreateCharacter();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = (characters ?? []).find((c) => c.id === selectedId);

  const handleCreate = async () => {
    const c = await createChar.mutateAsync({ project_id: pid, name: "未命名" });
    setSelectedId(c.id);
  };

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="人物"
          action={
            <Button variant="ghost" onClick={handleCreate} disabled={createChar.isPending}>
              + 新建
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-[#888] p-2">加载中...</p>
          ) : !characters || characters.length === 0 ? (
            <p className="text-xs text-[#888] p-2">还没有人物</p>
          ) : (
            characters.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedId(c.id)}
                className={`block w-full text-left px-3 py-2 rounded text-sm ${
                  selectedId === c.id
                    ? "bg-[#37373d] text-white"
                    : "hover:bg-[#2a2a2a] text-[#cccccc]"
                }`}
              >
                {c.name || "未命名"} <span className="text-[#888]">({c.role})</span>
              </button>
            ))
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto">
          <CharacterForm
            projectId={pid}
            character={selected}
            onDeleted={() => setSelectedId(null)}
          />
        </div>
      }
    />
  );
}
