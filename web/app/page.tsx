"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useProjects, useCreateProject, useGenreTemplates } from "@/lib/queries";
import { ProjectCard } from "@/components/entities/ProjectCard";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { SettingsButton } from "@/components/layout/SettingsButton";

export default function HomePage() {
  const router = useRouter();
  const toast = useToast();
  const { data: projects, isLoading } = useProjects();
  const createProject = useCreateProject();
  const { data: genreTemplates } = useGenreTemplates();
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newGenre, setNewGenre] = useState("");
  const [newPremise, setNewPremise] = useState("");
  // Default to preset; flipped to "custom" when user picks "自定义..."
  const [genreMode, setGenreMode] = useState<"preset" | "custom">("preset");

  // Reset modal state whenever the modal closes
  const closeModal = () => {
    setCreating(false);
    setNewTitle("");
    setNewGenre("");
    setNewPremise("");
    setGenreMode("preset");
  };

  // Close on Escape
  useEffect(() => {
    if (!creating) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeModal();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [creating]);

  const handleCreate = async () => {
    const trimmed = newTitle.trim();
    if (!trimmed) {
      toast("请输入标题", "error");
      return;
    }
    try {
      const p = await createProject.mutateAsync({
        title: trimmed,
        genre: newGenre.trim() || undefined,
        premise: newPremise.trim() || undefined,
      });
      closeModal();
      router.push(`/projects/${p.id}/chapters`);
    } catch (e) {
      toast(`创建失败: ${(e as Error).message}`, "error");
    }
  };

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl">NovelAI</h1>
          <div className="flex items-center gap-2">
            <SettingsButton />
            <ThemeToggle />
            <Button
              variant="primary"
              onClick={() => setCreating(true)}
              disabled={createProject.isPending}
            >
              + 新建项目
            </Button>
          </div>
        </div>

        {isLoading ? (
          <p className="text-text-muted">加载中...</p>
        ) : !projects || projects.length === 0 ? (
          <p className="text-text-muted">还没有项目。点右上角&quot;新建项目&quot;开始。</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </div>

      {creating && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={closeModal}
        >
          <div
            className="bg-panel border border-line rounded-lg shadow-lg w-full max-w-md p-4 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-text">新建项目</h2>

            <div>
              <label className="text-xs text-text-muted-bright block mb-1">
                标题 <span className="text-accent">*</span>
              </label>
              <input
                autoFocus
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleCreate();
                }}
                placeholder="给你的故事起个名字"
                className="w-full bg-input border border-line rounded px-2 py-1.5 text-base text-text"
              />
            </div>

            <div>
              <label className="text-xs text-text-muted-bright block mb-1">类型</label>
              {genreMode === "preset" ? (
                <select
                  value={newGenre && genreTemplates && newGenre in genreTemplates ? newGenre : ""}
                  onChange={(e) => {
                    if (e.target.value === "__custom__") {
                      setGenreMode("custom");
                      setNewGenre("");
                    } else {
                      setNewGenre(e.target.value);
                    }
                  }}
                  className="w-full bg-input border border-line rounded px-2 py-1.5 text-sm text-text"
                >
                  <option value="">不选择</option>
                  {genreTemplates &&
                    Object.entries(genreTemplates).map(([key, tpl]) => (
                      <option key={key} value={key}>
                        {tpl.label}
                      </option>
                    ))}
                  <option value="__custom__">自定义...</option>
                </select>
              ) : (
                <div className="flex gap-1">
                  <input
                    value={newGenre}
                    onChange={(e) => setNewGenre(e.target.value)}
                    placeholder="输入类型"
                    className="flex-1 bg-input border border-line rounded px-2 py-1.5 text-sm text-text"
                  />
                  <button
                    type="button"
                    onClick={() => setGenreMode("preset")}
                    title="返回预设列表"
                    className="px-2 py-1 rounded text-sm bg-button hover:bg-button-hover text-text"
                  >
                    ▾
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className="text-xs text-text-muted-bright block mb-1">
                前提 <span className="text-text-muted">(可选)</span>
              </label>
              <textarea
                value={newPremise}
                onChange={(e) => setNewPremise(e.target.value)}
                rows={2}
                placeholder="一句话概括你的故事"
                className="w-full bg-input border border-line rounded p-2 text-sm text-text"
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="subtle" onClick={closeModal}>
                取消
              </Button>
              <Button
                variant="primary"
                onClick={handleCreate}
                disabled={!newTitle.trim() || createProject.isPending}
              >
                创建
              </Button>
            </div>
            <p className="text-xs text-text-muted">Esc 取消 · Cmd/Ctrl+Enter 创建</p>
          </div>
        </div>
      )}
    </main>
  );
}
