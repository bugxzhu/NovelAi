"use client";

import Link from "next/link";
import { useState } from "react";
import type { Project } from "@/lib/types";
import { useUpdateProject, useDeleteProject, useGenreTemplates } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";

export function ProjectCard({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const del = useDeleteProject();
  const toast = useToast();
  const { data: genreTemplates } = useGenreTemplates();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(project.title);
  const [genre, setGenre] = useState(project.genre);
  const isPresetGenre = !!(genreTemplates && genre && genre in genreTemplates);
  const [genreMode, setGenreMode] = useState<"preset" | "custom">(
    isPresetGenre ? "preset" : "custom"
  );

  const save = () => {
    const trimmed = title.trim();
    if (!trimmed) {
      setTitle(project.title);
      setGenre(project.genre);
      setGenreMode(
        genreTemplates && project.genre && project.genre in genreTemplates ? "preset" : "custom"
      );
      setEditing(false);
      return;
    }
    const patch: { title?: string; genre?: string } = {};
    if (trimmed !== project.title) patch.title = trimmed;
    if (genre !== project.genre) patch.genre = genre;
    if (Object.keys(patch).length === 0) {
      setEditing(false);
      return;
    }
    update.mutate(patch, {
      onSuccess: () => setEditing(false),
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  };

  const cancelEdit = () => {
    setTitle(project.title);
    setGenre(project.genre);
    setGenreMode(
      genreTemplates && project.genre && project.genre in genreTemplates ? "preset" : "custom"
    );
    setEditing(false);
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`删除项目 "${project.title || "未命名"}"？所有章节、人物、设定将一并删除。`)) return;
    del.mutate(project.id, {
      onError: (e) => {
        const err = e as any;
        const detail = err?.body?.detail || err?.message || "未知错误";
        toast(`删除失败: ${detail}`, "error");
      },
    });
  };

  const startEdit = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setTitle(project.title);
    setGenre(project.genre);
    setGenreMode(
      genreTemplates && project.genre && project.genre in genreTemplates ? "preset" : "custom"
    );
    setEditing(true);
  };

  return (
    <div className="relative group bg-panel hover:bg-hover-strong border border-line rounded p-4 transition-colors">
      {/* Hover actions */}
      {!editing && (
        <div className="absolute top-2 right-2 hidden group-hover:flex gap-1">
          <button
            onClick={startEdit}
            title="编辑"
            className="w-6 h-6 flex items-center justify-center rounded text-xs bg-button hover:bg-button-hover text-text"
          >
            ✏️
          </button>
          <button
            onClick={handleDelete}
            title="删除"
            className="w-6 h-6 flex items-center justify-center rounded text-xs bg-button hover:bg-button-hover text-text"
          >
            🗑️
          </button>
        </div>
      )}

      {editing ? (
        <div onClick={(e) => e.preventDefault()}>
          <label className="text-xs text-text-muted-bright block mb-1">标题</label>
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancelEdit();
            }}
            className="w-full bg-input border border-accent rounded px-2 py-1 text-base font-semibold text-text mb-2"
          />
          <label className="text-xs text-text-muted-bright block mb-1">类型</label>
          {genreMode === "preset" ? (
            <select
              value={genre && genreTemplates && genre in genreTemplates ? genre : "__custom__"}
              onChange={(e) => {
                if (e.target.value === "__custom__") {
                  setGenreMode("custom");
                  setGenre("");
                } else {
                  setGenre(e.target.value);
                }
              }}
              className="w-full bg-input border border-line rounded px-2 py-1 text-sm text-text"
            >
              {!genre ||
              !genreTemplates ||
              !(genre in genreTemplates) ? null : (
                <option value={genre}>
                  {genreTemplates[genre]?.label ?? genre}
                </option>
              )}
              {genreTemplates &&
                Object.entries(genreTemplates)
                  .filter(([key]) => key !== genre)
                  .map(([key, tpl]) => (
                    <option key={key} value={key}>
                      {tpl.label}
                    </option>
                  ))}
              <option value="__custom__">自定义...</option>
            </select>
          ) : (
            <div className="flex gap-1">
              <input
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                placeholder="输入类型"
                className="flex-1 bg-input border border-line rounded px-2 py-1 text-sm text-text"
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
          <div className="flex gap-2 mt-3">
            <button
              type="button"
              onClick={save}
              className="px-3 py-1 rounded text-xs bg-accent text-white hover:opacity-90"
            >
              保存
            </button>
            <button
              type="button"
              onClick={cancelEdit}
              className="px-3 py-1 rounded text-xs bg-button hover:bg-button-hover text-text"
            >
              取消
            </button>
          </div>
          <p className="text-xs text-text-muted mt-2">回车保存 · Esc 取消</p>
        </div>
      ) : (
        <Link href={`/projects/${project.id}/chapters`} className="block">
          <h3 className="text-base font-semibold mb-1">{project.title || "未命名项目"}</h3>
          <p className="text-xs text-text-muted mb-2">
            {[project.genre, project.main_theme].filter(Boolean).join(" · ") || "无设定"}
          </p>
          <p className="text-xs text-text-dim line-clamp-2">{project.premise}</p>
        </Link>
      )}
    </div>
  );
}
