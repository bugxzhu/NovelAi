"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProjects, useCreateProject } from "@/lib/queries";
import { ProjectCard } from "@/components/entities/ProjectCard";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";

export default function HomePage() {
  const router = useRouter();
  const toast = useToast();
  const { data: projects, isLoading } = useProjects();
  const createProject = useCreateProject();
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const p = await createProject.mutateAsync({ title: "未命名项目" });
      router.push(`/projects/${p.id}/chapters`);
    } catch (e) {
      toast(`创建失败: ${(e as Error).message}`, "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl">NovelAI</h1>
          <Button variant="primary" onClick={handleCreate} disabled={creating}>
            + 新建项目
          </Button>
        </div>

        {isLoading ? (
          <p className="text-[#888]">加载中...</p>
        ) : !projects || projects.length === 0 ? (
          <p className="text-[#888]">还没有项目。点右上角&quot;新建项目&quot;开始。</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
