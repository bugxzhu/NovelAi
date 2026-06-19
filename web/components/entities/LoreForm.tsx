"use client";

import { useEffect, useState } from "react";
import { useLore, useUpdateLore, useDeleteLore } from "@/lib/queries";
import { debounce } from "@/lib/debounce";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import type { LoreEntry, LoreUpdate, LoreType } from "@/lib/types";

const TEXT_FIELDS: Array<{ key: keyof LoreUpdate; label: string; rows?: number }> = [
  { key: "name", label: "名称" },
  { key: "title", label: "别名" },
  { key: "description", label: "描述", rows: 4 },
];

export function LoreForm({
  projectId,
  lore,
  onDeleted,
}: {
  projectId: number;
  lore?: LoreEntry;
  onDeleted?: () => void;
}) {
  const update = useUpdateLore(lore?.id ?? 0, projectId);
  const del = useDeleteLore(projectId);
  const { data: allLore } = useLore(projectId);
  const toast = useToast();

  const [form, setForm] = useState<LoreUpdate>({});

  useEffect(() => {
    if (lore) {
      setForm({
        type: lore.type,
        name: lore.name,
        title: lore.title,
        description: lore.description,
        parent_id: lore.parent_id,
      });
    }
  }, [lore?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = debounce((value: LoreUpdate) => {
    if (!lore) return;
    update.mutate(value, {
      onError: (e) => toast(`保存失败: ${(e as Error).message}`, "error"),
    });
  }, 500);

  const setText = (key: keyof LoreUpdate, v: string) => {
    const next = { ...form, [key]: v };
    setForm(next);
    save(next);
  };

  if (!lore) {
    return <div className="p-4 text-[#888]">请从左侧选择或新建条目</div>;
  }

  // For locations, parent candidates are other locations of same project (excluding self + descendants)
  const sameTypeLocations = (allLore ?? []).filter(
    (l) => l.type === "location" && l.id !== lore.id
  );

  return (
    <div className="p-4 space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-lg">{form.name || lore.name || "未命名"}</h2>
        <Button
          variant="danger"
          onClick={() => {
            if (!confirm(`删除 "${lore.name}"？`)) return;
            del.mutate(lore.id, {
              onSuccess: () => onDeleted?.(),
              onError: (e) => toast(`删除失败: ${(e as Error).message}`, "error"),
            });
          }}
        >
          删除
        </Button>
      </div>

      <div>
        <label className="text-xs text-[#aaa] block mb-1">类型</label>
        <select
          value={(form.type as LoreType) ?? lore.type}
          onChange={(e) => {
            const v = e.target.value as LoreType;
            setForm({ ...form, type: v });
            save({ ...form, type: v });
          }}
          className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
        >
          {["location", "faction", "item", "organization", "concept", "custom"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {TEXT_FIELDS.map((f) => (
        <div key={f.key}>
          <label className="text-xs text-[#aaa] block mb-1">{f.label}</label>
          {f.rows ? (
            <textarea
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              rows={f.rows}
              className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
            />
          ) : (
            <input
              value={(form[f.key] as string) ?? ""}
              onChange={(e) => setText(f.key, e.target.value)}
              className="w-full bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
            />
          )}
        </div>
      ))}

      {lore.type === "location" && (
        <div>
          <label className="text-xs text-[#aaa] block mb-1">上级地点</label>
          <select
            value={form.parent_id ?? lore.parent_id ?? ""}
            onChange={(e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              setForm({ ...form, parent_id: v });
              save({ ...form, parent_id: v });
            }}
            className="bg-[#1e1e1e] border border-[#3c3c3c] rounded p-2 text-[#cccccc]"
          >
            <option value="">（顶级）</option>
            {sameTypeLocations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
