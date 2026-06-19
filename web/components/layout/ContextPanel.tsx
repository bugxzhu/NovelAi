"use client";

import { useCharacters, useLore } from "@/lib/queries";
import { useGenerateParams } from "@/lib/store";

export function ContextPanel({ projectId }: { projectId: number }) {
  const { involvedCharacterIds, locationId } = useGenerateParams();
  const { data: characters } = useCharacters(projectId);
  const { data: allLore } = useLore(projectId);

  const involvedChars = (characters ?? []).filter((c) => involvedCharacterIds.includes(c.id));
  const location = (allLore ?? []).find((l) => l.id === locationId);
  const factionIds = new Set<number>();
  for (const c of involvedChars) for (const fid of c.affiliations ?? []) factionIds.add(fid);
  const factions = (allLore ?? []).filter((l) => l.type === "faction" && factionIds.has(l.id));

  return (
    <div className="h-full overflow-y-auto p-3 text-sm">
      <h3 className="text-xs uppercase text-text-muted mb-3">📋 当前场景</h3>

      <Section title="人物">
        {involvedChars.length === 0 ? (
          <Empty>未选</Empty>
        ) : (
          involvedChars.map((c) => (
            <div key={c.id} className="text-text">
              · {c.name}
              <span className="text-text-muted"> （{c.role}）</span>
            </div>
          ))
        )}
      </Section>

      <Section title="地点">
        {location ? (
          <div className="text-text">· {location.name}</div>
        ) : (
          <Empty>未选</Empty>
        )}
      </Section>

      <Section title="势力">
        {factions.length === 0 ? (
          <Empty>无</Empty>
        ) : (
          factions.map((f) => <div key={f.id} className="text-text">· {f.name}</div>)
        )}
      </Section>

      <div className="mt-6 p-2 bg-input rounded text-xs text-text-muted">
        💡 这是 AI 生成时将看到的常驻层。点人物/地点可在底部生成面板中调整。
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-xs text-text-muted-bright mb-1">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-text-dim text-xs">{children}</div>;
}
