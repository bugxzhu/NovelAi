"use client";

import Link from "next/link";
import type { Project } from "@/lib/types";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/projects/${project.id}/chapters`}
      className="block bg-panel hover:bg-hover-strong border border-line rounded p-4 transition-colors"
    >
      <h3 className="text-base font-semibold mb-1">{project.title || "未命名项目"}</h3>
      <p className="text-xs text-text-muted mb-2">
        {[project.genre, project.main_theme].filter(Boolean).join(" · ") || "无设定"}
      </p>
      <p className="text-xs text-text-dim line-clamp-2">{project.premise}</p>
    </Link>
  );
}
