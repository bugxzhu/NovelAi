"use client";

import Link from "next/link";
import type { Project } from "@/lib/types";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/projects/${project.id}/chapters`}
      className="block bg-[#252526] hover:bg-[#2d2d2d] border border-[#3c3c3c] rounded p-4 transition-colors"
    >
      <h3 className="text-base font-semibold mb-1">{project.title || "未命名项目"}</h3>
      <p className="text-xs text-[#888] mb-2">
        {[project.genre, project.main_theme].filter(Boolean).join(" · ") || "无设定"}
      </p>
      <p className="text-xs text-[#666] line-clamp-2">{project.premise}</p>
    </Link>
  );
}
