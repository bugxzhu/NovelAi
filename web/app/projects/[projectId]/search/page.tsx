"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { useChapters, useCharacters, useLore } from "@/lib/queries";
import { SidePanel } from "@/components/layout/SidePanel";
import { ChapterWorkspaceGrid } from "@/components/layout/ChapterWorkspaceGrid";
import Link from "next/link";

export default function SearchPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);
  const [q, setQ] = useState("");
  const { data: chapters } = useChapters(pid);
  const { data: characters } = useCharacters(pid);
  const { data: lore } = useLore(pid);

  const needle = q.trim().toLowerCase();
  const match = (s: string | undefined | null) =>
    !!needle && !!s && s.toLowerCase().includes(needle);

  const chapterHits = (chapters ?? []).filter(
    (c) => match(c.title) || match(c.content) || match(c.outline)
  );
  const charHits = (characters ?? []).filter(
    (c) => match(c.name) || match(c.background) || match(c.motivation)
  );
  const loreHits = (lore ?? []).filter(
    (l) => match(l.name) || match(l.description)
  );

  return (
    <ChapterWorkspaceGrid
      sidePanel={
        <SidePanel title="搜索">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索章节/人物/设定…"
            className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc] text-sm"
          />
        </SidePanel>
      }
      editor={
        <div className="h-full overflow-y-auto p-4 text-sm space-y-4">
          {!needle ? (
            <p className="text-[#888]">输入关键字搜索项目内容（substring 匹配）</p>
          ) : (
            <>
              <Section title={`章节 (${chapterHits.length})`}>
                {chapterHits.map((c) => (
                  <Link
                    key={c.id}
                    href={`/projects/${pid}/chapters/${c.id}`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {c.title} <span className="text-[#888]">#{c.id}</span>
                  </Link>
                ))}
              </Section>
              <Section title={`人物 (${charHits.length})`}>
                {charHits.map((c) => (
                  <Link
                    key={c.id}
                    href={`/projects/${pid}/characters`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {c.name} <span className="text-[#888]">({c.role})</span>
                  </Link>
                ))}
              </Section>
              <Section title={`设定 (${loreHits.length})`}>
                {loreHits.map((l) => (
                  <Link
                    key={l.id}
                    href={`/projects/${pid}/lore`}
                    className="block px-2 py-1 hover:bg-[#2a2a2a] rounded"
                  >
                    {l.name} <span className="text-[#888]">({l.type})</span>
                  </Link>
                ))}
              </Section>
            </>
          )}
        </div>
      }
    />
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-xs text-[#888] mb-1">{title}</h3>
      {children}
    </div>
  );
}
