"use client";

import Link from "next/link";
import { useState } from "react";
import type { Project } from "@/lib/types";
import { useUpdateProject, useDeleteProject } from "@/lib/queries";
import { useToast } from "@/components/ui/Toast";

export function ProjectCard({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const del = useDeleteProject();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(project.title);

  const save = () => {
    const trimmed = title.trim();
    if (!trimmed || trimmed === project.title) {
      setTitle(project.title);
      setEditing(false);
      return;
    }
    update.mutate(
      { title: trimmed },
      {
        onSuccess: () => setEditing(false),
        onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
      }
    );
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
    setEditing(true);
  };

  return (
    <div className="relative group bg-panel hover:bg-hover-strong border border-line rounded p-4 transition-colors">
      {/* Hover actions */}
      {!editing && (
        <div className="absolute top-2 right-2 hidden group-hover:flex gap-1">
          <button
            onClick={startEdit}
            title="重命名"
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
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={save}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") {
                setTitle(project.title);
                setEditing(false);
              }
            }}
            className="w-full bg-input border border-accent rounded px-2 py-1 text-base font-semibold text-text mb-1"
          />
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
