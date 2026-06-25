"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useChapterVersions, useChapterVersion } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import { VersionListItem } from "@/components/versions/VersionListItem";
import { VersionPreview } from "@/components/versions/VersionPreview";
import { VersionRestoreButton } from "@/components/versions/VersionRestoreButton";
import { Button } from "@/components/ui/Button";

export default function ChapterVersionsPage() {
  const params = useParams<{ projectId: string; chapterId: string }>();
  const router = useRouter();
  const pid = Number(params.projectId);
  const cid = Number(params.chapterId);
  const { data: versions, isLoading } = useChapterVersions(cid);
  const [selectedId, setSelectedId] = useState<number | null>(
    versions?.[0]?.id ?? null
  );
  const { data: selected, isLoading: detailLoading } = useChapterVersion(
    selectedId ?? 0
  );

  useEffect(() => {
    if (versions && versions.length > 0 && selectedId === null) {
      setSelectedId(versions[0].id);
    }
  }, [versions, selectedId]);

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel
          title="版本历史"
          action={
            <Button variant="ghost" onClick={() => router.back()}>
              ← 返回
            </Button>
          }
        >
          {isLoading ? (
            <p className="text-xs text-text-muted p-2">加载中...</p>
          ) : !versions || versions.length === 0 ? (
            <div className="p-2">
              <p className="text-xs text-text-muted mb-2">还没有版本。</p>
              <p className="text-xs text-text-dim">
                返回编辑器写一些后用 <span className="text-text">💾</span> 存版本。
              </p>
              <Link
                href={`/projects/${pid}/chapters/${cid}`}
                className="text-xs text-accent hover:underline mt-2 inline-block"
              >
                ← 返回编辑器
              </Link>
            </div>
          ) : (
            <div className="space-y-0.5">
              {versions.map((v) => (
                <VersionListItem
                  key={v.id}
                  version={v}
                  selected={v.id === selectedId}
                  onSelect={setSelectedId}
                />
              ))}
            </div>
          )}
        </SidePanel>
      }
      editor={
        <div className="h-full flex flex-col">
          <div className="flex-1 min-h-0">
            <VersionPreview version={selected ?? null} loading={detailLoading} />
          </div>
          {selectedId !== null && (
            <div className="shrink-0 border-t border-line bg-panel px-4 py-2 flex justify-end">
              <VersionRestoreButton versionId={selectedId} chapterId={cid} projectId={pid} />
            </div>
          )}
        </div>
      }
    />
  );
}
