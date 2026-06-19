"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ProjectHomePage() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/projects/${params.projectId}/chapters`);
  }, [params.projectId, router]);
  return <div className="p-4 text-text-muted">加载中...</div>;
}
