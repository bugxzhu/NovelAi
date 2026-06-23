"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { SearchResults } from "@/lib/types";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";

export default function SearchPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api.search(pid, query.trim());
      setResults(r);
    } catch (e) {
      setError(e instanceof ApiError ? `搜索失败 (HTTP ${e.status})` : "搜索失败");
    } finally {
      setLoading(false);
    }
  };

  const total = results
    ? results.chapters.length + results.characters.length +
      results.lore.length + results.events.length
    : 0;

  return (
    <ChapterWorkspaceGrid
      sidePanel={<SidePanel title="搜索"><></></SidePanel>}
      editor={
        <div className="h-full overflow-y-auto p-4">
          <div className="max-w-2xl mx-auto">
            <div className="flex gap-2 mb-4">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="搜索章节/人物/设定/事件..."
                className="flex-1 bg-input border border-line rounded px-3 py-2 text-text"
                autoFocus
              />
              <button
                onClick={handleSearch}
                disabled={loading || !query.trim()}
                className="px-4 py-2 rounded bg-accent text-white text-sm disabled:opacity-50"
              >
                {loading ? "..." : "搜索"}
              </button>
            </div>

            {error && (
              <p className="text-sm text-red-500 mb-4">{error}</p>
            )}

            {results && (
              <div className="space-y-4">
                <p className="text-xs text-text-muted">共 {total} 条结果</p>

                {results.chapters.length > 0 && (
                  <div>
                    <h3 className="text-sm text-text-muted-bright mb-2">
                      章节（{results.chapters.length}）
                    </h3>
                    {results.chapters.map((ch) => (
                      <Link
                        key={ch.id}
                        href={`/projects/${pid}/chapters/${ch.id}`}
                        className="block p-2 hover:bg-hover rounded text-sm"
                      >
                        <div className="text-text">
                          第 {ch.order_index} 章 · {ch.title}
                          <span className="ml-2 text-xs text-text-muted">[{ch.match_type}]</span>
                        </div>
                        {ch.snippet && (
                          <div className="text-xs text-text-dim mt-1 whitespace-pre-wrap">
                            {ch.snippet}
                          </div>
                        )}
                      </Link>
                    ))}
                  </div>
                )}

                {results.characters.length > 0 && (
                  <div>
                    <h3 className="text-sm text-text-muted-bright mb-2">
                      人物（{results.characters.length}）
                    </h3>
                    {results.characters.map((c) => (
                      <Link
                        key={c.id}
                        href={`/projects/${pid}/characters`}
                        className="block p-2 hover:bg-hover rounded text-sm text-text"
                      >
                        {c.name}{" "}
                        <span className="text-text-muted">({c.role || "—"})</span>
                      </Link>
                    ))}
                  </div>
                )}

                {results.lore.length > 0 && (
                  <div>
                    <h3 className="text-sm text-text-muted-bright mb-2">
                      设定（{results.lore.length}）
                    </h3>
                    {results.lore.map((l) => (
                      <Link
                        key={l.id}
                        href={`/projects/${pid}/lore`}
                        className="block p-2 hover:bg-hover rounded text-sm text-text"
                      >
                        [{l.type}] {l.name}
                      </Link>
                    ))}
                  </div>
                )}

                {results.events.length > 0 && (
                  <div>
                    <h3 className="text-sm text-text-muted-bright mb-2">
                      事件（{results.events.length}）
                    </h3>
                    {results.events.map((e) => (
                      <Link
                        key={e.id}
                        href={`/projects/${pid}/events`}
                        className="block p-2 hover:bg-hover rounded text-sm text-text"
                      >
                        {e.name}
                        {e.description && (
                          <div className="text-xs text-text-dim mt-1">{e.description}</div>
                        )}
                      </Link>
                    ))}
                  </div>
                )}

                {total === 0 && (
                  <p className="text-text-muted">未找到匹配结果</p>
                )}
              </div>
            )}
          </div>
        </div>
      }
    />
  );
}
